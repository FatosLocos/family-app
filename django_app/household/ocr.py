import re

from PIL import Image
import pytesseract

from household.models import Receipt


def process_receipt(receipt_id):
    receipt = Receipt.objects.select_related("household").get(pk=receipt_id)
    if receipt.image.name.lower().endswith(".pdf"):
        receipt.ocr_status = Receipt.OcrStatus.FAILED
        receipt.ocr_error = "PDF-herkenning is nog niet beschikbaar; vul winkel en totaal handmatig in."
        receipt.save(update_fields=["ocr_status", "ocr_error", "updated_at"])
        return
    try:
        with Image.open(receipt.image.path) as image:
            text = pytesseract.image_to_string(image, lang="nld+eng")
        receipt.ocr_text = text[:20000]
        receipt.ocr_status = Receipt.OcrStatus.COMPLETE
        receipt.ocr_error = ""
        if not receipt.total_amount:
            match = re.search(r"(?:totaal|total)\D{0,18}(\d+[,.]\d{2})", text, re.IGNORECASE)
            if match:
                from decimal import Decimal
                receipt.total_amount = Decimal(match.group(1).replace(",", "."))
        receipt.save(update_fields=["ocr_text", "ocr_status", "ocr_error", "total_amount", "updated_at"])
    except Exception:
        receipt.ocr_status = Receipt.OcrStatus.FAILED
        receipt.ocr_error = "Tekstherkenning kon deze bon niet lezen."
        receipt.save(update_fields=["ocr_status", "ocr_error", "updated_at"])
