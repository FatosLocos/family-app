from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
import xlrd

DATE_KEYS = {"boekdatum", "datum", "transactiedatum", "valutadatum", "rentedatum"}
AMOUNT_KEYS = {"bedrag", "mutatiebedrag", "transactiebedrag", "bedrag eur"}
DESCRIPTION_KEYS = {"omschrijving", "description", "mededelingen", "details", "transactieomschrijving"}
ACCOUNT_KEYS = {"rekeningnummer", "iban", "rekening"}
CURRENCY_KEYS = {"muntsoort", "valuta", "currency"}


def normalized(value: object) -> str:
    value = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def rows_for_upload(upload) -> list[list[str]]:
    data = upload.read()
    upload.seek(0)
    name = upload.name.lower()
    if name.endswith(".xlsx"):
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        return [[str(cell or "").strip() for cell in row] for sheet in workbook.worksheets for row in sheet.iter_rows(values_only=True)]
    if name.endswith(".xls"):
        workbook = xlrd.open_workbook(file_contents=data)
        return [
            [str(cell.value or "").strip() for cell in row]
            for sheet_index in range(workbook.nsheets)
            for row in workbook.sheet_by_index(sheet_index).get_rows()
        ]
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=";,\t") if sample else csv.excel
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]


def _find_header(rows: list[list[str]]) -> int:
    best_index, best_score = -1, 0
    for index, row in enumerate(rows):
        fields = {normalized(value) for value in row}
        score = 2 * bool(fields & DATE_KEYS) + 2 * bool(fields & AMOUNT_KEYS) + bool(fields & DESCRIPTION_KEYS) + bool(fields & ACCOUNT_KEYS)
        if score > best_score:
            best_index, best_score = index, score
    return best_index if best_score >= 4 else -1


def _parse_amount(value: str) -> Decimal | None:
    value = value.replace("EUR", "").replace("€", "").replace(" ", "").replace("+", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_date(value: str) -> date | None:
    value = str(value).strip()
    for layout in ("%Y%m%d", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:10], layout).date()
        except ValueError:
            continue
    return None


def parse_description(value: str) -> tuple[str, str, dict[str, str]]:
    compact = re.sub(r"\s+", " ", value).strip()
    metadata: dict[str, str] = {}
    if compact.startswith("BEA,"):
        parts = [part.strip() for part in compact.split(",") if part.strip()]
        metadata["payment_type"] = parts[0]
        if len(parts) > 1:
            metadata["method"] = parts[1]
        for part in parts[2:]:
            if part.startswith("PAS"):
                metadata["card"] = part
            elif "NR:" in part:
                metadata["transaction_number"] = part
        counterparty = next((part for part in parts[2:] if not part.startswith("PAS") and "NR:" not in part and not re.match(r"\d{2}\.\d{2}", part)), "")
        return compact, counterparty, metadata
    if "/" in compact:
        segments = [segment.strip() for segment in compact.split("/") if segment.strip()]
        counterparty = ""
        for index, segment in enumerate(segments[:-1]):
            if segment.upper() in {"NAME", "NM", "BENM"}:
                counterparty = segments[index + 1]
            elif segment.upper() in {"TRTP", "CSID", "MARF", "REMI", "EREF"}:
                metadata[segment.lower()] = segments[index + 1]
        if segments:
            metadata.setdefault("payment_type", segments[0])
        return compact, counterparty, metadata
    return compact, "", metadata


def parse_abn_rows(rows: list[list[str]], fallback_account: str) -> tuple[str, list[dict], int]:
    header_index = _find_header(rows)
    if header_index < 0:
        raise ValueError("Geen herkenbare ABN AMRO-header gevonden.")
    headers = [normalized(value) for value in rows[header_index]]
    transactions, skipped, account_identifier = [], 0, fallback_account
    for position, row in enumerate(rows[header_index + 1:]):
        raw = {headers[index] or f"kolom_{index}": (row[index] if index < len(row) else "") for index in range(len(headers))}
        date_value = next((raw[key] for key in raw if key in DATE_KEYS and raw[key]), "")
        amount_value = next((raw[key] for key in raw if key in AMOUNT_KEYS and raw[key]), "")
        description = next((raw[key] for key in raw if key in DESCRIPTION_KEYS and raw[key]), "")
        account = next((raw[key] for key in raw if key in ACCOUNT_KEYS and raw[key]), "")
        booked_at, amount = _parse_date(date_value), _parse_amount(amount_value)
        if not booked_at or amount is None:
            skipped += 1
            continue
        account_identifier = account or account_identifier
        description, counterparty, metadata = parse_description(description or "ABN AMRO transactie")
        metadata["source"] = "abn_amro_manual"
        fingerprint = hashlib.sha256(f"{account_identifier}|{booked_at}|{amount}|{description}|{position}".encode()).hexdigest()
        transactions.append({"provider_transaction_id": fingerprint, "booked_at": booked_at, "amount": amount, "description": description, "counterparty": counterparty, "payment_type": metadata.get("payment_type", ""), "metadata": {**metadata, "raw": raw}})
    return account_identifier, transactions, skipped
