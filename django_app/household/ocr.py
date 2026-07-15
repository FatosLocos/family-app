import re
import subprocess
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
import pytesseract

from household.models import Receipt, ReceiptLineItem, ShoppingItem
from household.receipt_matching import match_receipt_to_transaction


def _receipt_text(path: str) -> str:
    if not path.lower().endswith(".pdf"):
        with Image.open(path) as image:
            return pytesseract.image_to_string(image, lang="nld+eng")

    with TemporaryDirectory(prefix="family-app-receipt-") as directory:
        prefix = Path(directory) / "page"
        subprocess.run(
            ["pdftoppm", "-f", "1", "-l", "1", "-r", "220", "-png", path, str(prefix)],
            check=True,
            timeout=45,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        page = next(Path(directory).glob("page-*.png"), None)
        if page is None:
            raise RuntimeError("PDF bevat geen leesbare pagina.")
        with Image.open(page) as image:
            return pytesseract.image_to_string(image, lang="nld+eng")


_RECEIPT_LINE_RE = re.compile(
    r"^(?P<name>[A-Z0-9À-ÖØ-Ý][A-Z0-9À-ÖØ-Ý .'&/+-]{1,220}?)\s{2,}(?P<price>\d{1,5}[,.]\d{2})\s*$",
    re.IGNORECASE,
)
_QUANTITY_PREFIX_RE = re.compile(r"^(?P<quantity>\d+(?:[,.]\d+)?)\s*(?:x|\*)\s+(?P<name>.+)$", re.IGNORECASE)
_NON_PRODUCT_TOKENS = frozenset({
    "afrekenen", "betaling", "betaald", "btw", "cash", "contant", "korting", "mastercard",
    "maestro", "pinnen", "pin", "rekening", "subtotaal", "totaal", "total", "visa", "wisselgeld",
})
_RETAILER_MARKERS = (
    ("Albert Heijn", ("albert heijn", "ah.nl")),
    ("Jumbo", ("jumbo",)),
    ("Lidl", ("lidl",)),
    ("Kaufland", ("kaufland",)),
)


def _money(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _product_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", without_accents)


def _receipt_retailer(text: str) -> str:
    header = "\n".join(text.splitlines()[:12]).casefold()
    for retailer, markers in _RETAILER_MARKERS:
        if any(marker in header for marker in markers):
            return retailer
    return ""


def _receipt_purchase_date(text: str) -> date | None:
    """Accept common receipt dates, but never invent a date from partial OCR."""
    for raw_year, raw_month, raw_day in re.findall(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text):
        try:
            return date(int(raw_year), int(raw_month), int(raw_day))
        except ValueError:
            continue
    for raw_day, raw_month, raw_year in re.findall(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", text):
        year = int(raw_year)
        if year < 100:
            year += 2000
        try:
            parsed = date(year, int(raw_month), int(raw_day))
        except ValueError:
            continue
        if 2000 <= parsed.year <= date.today().year + 1:
            return parsed
    return None


def _receipt_shopping_matches(household, recognized_items: list[dict]) -> dict[str, ShoppingItem]:
    """Link only exact normalised names; OCR must not guess grocery identity."""
    keys = {_product_key(item["name"]) for item in recognized_items}
    matches: dict[str, ShoppingItem] = {}
    for item in ShoppingItem.objects.for_household(household).order_by("completed_at", "-created_at"):
        key = _product_key(item.name)
        if key in keys and key not in matches:
            matches[key] = item
    return matches


def parse_receipt_line_items(text: str) -> list[dict]:
    """Extract unambiguous product-and-price rows from common Dutch receipts."""
    items: list[dict] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        match = _RECEIPT_LINE_RE.match(raw_line.strip())
        if not match or not line:
            continue
        name = " ".join(match.group("name").split())
        normalized_name = name.casefold()
        if any(token in normalized_name for token in _NON_PRODUCT_TOKENS):
            continue
        price = _money(match.group("price"))
        if price is None or price <= 0:
            continue
        quantity = None
        quantity_match = _QUANTITY_PREFIX_RE.match(name)
        if quantity_match:
            quantity = _money(quantity_match.group("quantity"))
            name = quantity_match.group("name").strip()
        if len(name) < 2 or not any(character.isalpha() for character in name):
            continue
        unit_price = (price / quantity).quantize(Decimal("0.01")) if quantity and quantity > 0 else None
        items.append({"name": name[:240], "quantity": quantity, "unit_price": unit_price, "total_price": price, "raw_line": raw_line.strip()[:500]})
    return items[:100]


def process_receipt(receipt_id):
    receipt = Receipt.objects.select_related("household").get(pk=receipt_id)
    try:
        text = _receipt_text(receipt.image.path)
        receipt.ocr_text = text[:20000]
        receipt.ocr_status = Receipt.OcrStatus.COMPLETE
        receipt.ocr_error = ""
        if not receipt.retailer:
            receipt.retailer = _receipt_retailer(text)
        if not receipt.purchased_on:
            receipt.purchased_on = _receipt_purchase_date(text)
        if not receipt.total_amount:
            match = re.search(r"(?:totaal|total)\D{0,18}(\d+[,.]\d{2})", text, re.IGNORECASE)
            if match:
                receipt.total_amount = Decimal(match.group(1).replace(",", "."))
        receipt.save(update_fields=["ocr_text", "ocr_status", "ocr_error", "retailer", "purchased_on", "total_amount", "updated_at"])
        recognized_items = parse_receipt_line_items(text)
        shopping_matches = _receipt_shopping_matches(receipt.household, recognized_items)
        receipt.line_items.all().delete()
        ReceiptLineItem.objects.bulk_create(
            [
                ReceiptLineItem(
                    household=receipt.household,
                    receipt=receipt,
                    shopping_item=shopping_matches.get(_product_key(item["name"])),
                    **item,
                )
                for item in recognized_items
            ]
        )
        match_receipt_to_transaction(receipt)
    except Exception:
        receipt.ocr_status = Receipt.OcrStatus.FAILED
        receipt.ocr_error = "Tekstherkenning kon deze bon niet lezen."
        receipt.save(update_fields=["ocr_status", "ocr_error", "updated_at"])
