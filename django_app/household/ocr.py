import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
import pytesseract

from household.models import Receipt
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


def process_receipt(receipt_id):
    receipt = Receipt.objects.select_related("household").get(pk=receipt_id)
    try:
        text = _receipt_text(receipt.image.path)
        receipt.ocr_text = text[:20000]
        receipt.ocr_status = Receipt.OcrStatus.COMPLETE
        receipt.ocr_error = ""
        if not receipt.total_amount:
            match = re.search(r"(?:totaal|total)\D{0,18}(\d+[,.]\d{2})", text, re.IGNORECASE)
            if match:
                from decimal import Decimal
                receipt.total_amount = Decimal(match.group(1).replace(",", "."))
        receipt.save(update_fields=["ocr_text", "ocr_status", "ocr_error", "total_amount", "updated_at"])
        match_receipt_to_transaction(receipt)
    except Exception:
        receipt.ocr_status = Receipt.OcrStatus.FAILED
        receipt.ocr_error = "Tekstherkenning kon deze bon niet lezen."
        receipt.save(update_fields=["ocr_status", "ocr_error", "updated_at"])
