import * as XLSX from "xlsx";

export type ParsedAbnTransaction = {
  providerTransactionId: string;
  bookedAt: string;
  description: string;
  counterparty: string | null;
  amountCents: number;
  currency: string;
  raw: Record<string, string>;
};

export type ParsedAbnStatement = {
  accountName: string;
  accountIdentifier: string;
  iban: string | null;
  transactions: ParsedAbnTransaction[];
  skippedRows: number;
};

const DATE_KEYS = ["boekdatum", "datum", "transactiedatum", "valutadatum", "rentedatum", "date"];
const AMOUNT_KEYS = ["bedrag", "amount", "mutatiebedrag", "transactiebedrag", "transaction amount", "bedrag eur"];
const CREDIT_KEYS = ["bij", "credit", "credit amount", "bijschrijving"];
const DEBIT_KEYS = ["af", "debit", "debit amount", "afschrijving"];
const DIRECTION_KEYS = ["af bij", "afbij", "debet credit", "debet credit indicator"];
const DESCRIPTION_KEYS = ["omschrijving", "description", "mededelingen", "details", "naam omschrijving", "naam / omschrijving", "transactieomschrijving"];
const COUNTERPARTY_KEYS = ["tegenrekening naam", "naam tegenpartij", "counterparty", "tegenrekeninghouder", "naam"];
const IBAN_KEYS = ["rekeningnummer", "iban", "account", "rekening"];
const CURRENCY_KEYS = ["muntsoort", "valuta", "currency"];

export function parseAbnAmroStatement(text: string, fallbackName = "ABN AMRO import"): ParsedAbnStatement {
  const normalized = text.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (!normalized) return { accountName: fallbackName, accountIdentifier: fallbackName, iban: null, transactions: [], skippedRows: 0 };

  const lines = normalized.split("\n").filter((line) => line.trim());
  const delimiter = detectDelimiter(lines.slice(0, 10));
  const rows = lines.map((line) => parseDelimitedLine(line, delimiter));
  return parseAbnAmroRows(rows, fallbackName);
}

export function parseAbnAmroWorkbook(buffer: ArrayBuffer, fallbackName = "ABN AMRO import"): ParsedAbnStatement {
  const workbook = XLSX.read(buffer, { type: "array", cellDates: false, dense: false });
  const parsedSheets = workbook.SheetNames.flatMap((sheetName) => {
    const sheet = workbook.Sheets[sheetName];
    if (!sheet) return [];
    const rawRows = XLSX.utils.sheet_to_json<Array<string | number | boolean | Date | null>>(sheet, {
      header: 1,
      blankrows: false,
      defval: "",
      raw: true,
    });
    try {
      return [
        parseAbnAmroRows(
          rawRows.map((row) => row.map(formatWorkbookCell)),
          fallbackName,
        ),
      ];
    } catch {
      return [];
    }
  });
  const best = parsedSheets.sort((a, b) => b.transactions.length - a.transactions.length)[0];
  if (!best) throw new Error("Geen herkenbare ABN AMRO afschrift-header gevonden. Controleer of het Excel-bestand een werkblad met transacties bevat.");
  return best;
}

function parseAbnAmroRows(rows: string[][], fallbackName: string): ParsedAbnStatement {
  const headerIndex = findHeaderIndex(rows);
  if (headerIndex === -1) throw new Error("Geen herkenbare ABN AMRO afschrift-header gevonden. Controleer of het eerste werkblad transactiekolommen bevat.");

  const headers = rows[headerIndex].map(normalizeKey);
  const dataRows = rows.slice(headerIndex + 1);
  const ibanFromHeader = findMetaIban(rows.slice(0, headerIndex));
  let accountIban: string | null = ibanFromHeader;
  let accountIdentifier: string | null = accountIban;
  let skippedRows = 0;

  const transactions = dataRows
    .map((row, index) => {
      const raw = Object.fromEntries(headers.map((header, cellIndex) => [header || `kolom_${cellIndex + 1}`, row[cellIndex]?.trim() ?? ""]));
      row.slice(headers.length).forEach((cell, extraIndex) => {
        if (cell.trim()) raw[`extra_${extraIndex + 1}`] = cell.trim();
      });
      const bookedAt = parseDate(firstValue(raw, DATE_KEYS));
      const amountCents = parseAmountCents(raw);
      const descriptionBase = firstValue(raw, DESCRIPTION_KEYS) || firstNonEmpty(row.slice(3)) || "ABN AMRO transactie";
      const description = [descriptionBase, ...Object.entries(raw).filter(([key]) => key.startsWith("extra_")).map(([, value]) => value)]
        .filter(Boolean)
        .join(" ");
      const currency = firstValue(raw, CURRENCY_KEYS) || "EUR";
      const accountNumber = firstValue(raw, IBAN_KEYS);
      if (accountNumber && !accountIdentifier) accountIdentifier = normalizeAccountIdentifier(accountNumber);
      if (accountNumber && looksLikeIban(accountNumber) && !accountIban) accountIban = accountNumber.replace(/\s+/g, "").toUpperCase();
      if (!bookedAt || amountCents === null) {
        skippedRows += 1;
        return null;
      }
      const counterparty = firstValue(raw, COUNTERPARTY_KEYS);
      return {
        providerTransactionId: stableTransactionId([accountIban ?? fallbackName, bookedAt, String(amountCents), description, counterparty ?? "", String(index)]),
        bookedAt,
        description: compact(description),
        counterparty: counterparty ? compact(counterparty) : null,
        amountCents,
        currency: currency.toUpperCase(),
        raw,
      };
    })
    .filter((item): item is ParsedAbnTransaction => Boolean(item));

  return {
    accountName: accountIdentifier ? `ABN AMRO ${accountIdentifier.slice(-4)}` : fallbackName,
    accountIdentifier: accountIdentifier ?? fallbackName,
    iban: accountIban,
    transactions,
    skippedRows,
  };
}

function detectDelimiter(lines: string[]) {
  const candidates = [";", ",", "\t"];
  return candidates
    .map((delimiter) => ({ delimiter, score: lines.reduce((sum, line) => sum + line.split(delimiter).length, 0) }))
    .sort((a, b) => b.score - a.score)[0]?.delimiter ?? ";";
}

function parseDelimitedLine(line: string, delimiter: string) {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === delimiter && !quoted) {
      cells.push(cell);
      cell = "";
    } else {
      cell += char;
    }
  }
  cells.push(cell);
  return cells;
}

function normalizeKey(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function firstValue(raw: Record<string, string>, keys: string[]) {
  for (const [header, value] of Object.entries(raw)) {
    if (matchesAnyKey(header, keys) && value.trim()) return value.trim();
  }
  return null;
}

function findHeaderIndex(rows: string[][]) {
  let best = { index: -1, score: 0 };
  rows.forEach((row, index) => {
    const keys = row.map(normalizeKey);
    const score =
      (keys.some((key) => matchesAnyKey(key, DATE_KEYS)) ? 2 : 0) +
      (keys.some((key) => matchesAnyKey(key, AMOUNT_KEYS)) ? 2 : 0) +
      (keys.some((key) => matchesAnyKey(key, DESCRIPTION_KEYS)) ? 1 : 0) +
      (keys.some((key) => matchesAnyKey(key, IBAN_KEYS)) ? 1 : 0) +
      (keys.some((key) => matchesAnyKey(key, DIRECTION_KEYS)) ? 1 : 0);
    if (score > best.score) best = { index, score };
  });
  return best.score >= 4 ? best.index : -1;
}

function matchesAnyKey(header: string, keys: string[]) {
  const normalizedHeader = normalizeKey(header);
  return keys.some((key) => {
    const normalizedKey = normalizeKey(key);
    return normalizedHeader === normalizedKey || normalizedHeader.includes(normalizedKey);
  });
}

function firstNonEmpty(values: string[]) {
  return values.map((value) => value.trim()).find(Boolean) ?? null;
}

function parseDate(input: string | null) {
  if (!input) return null;
  const value = input.trim();
  if (/^\d{5}(?:\.\d+)?$/.test(value)) {
    const parsed = XLSX.SSF.parse_date_code(Number(value));
    if (parsed?.y && parsed?.m && parsed?.d) {
      return `${String(parsed.y).padStart(4, "0")}-${String(parsed.m).padStart(2, "0")}-${String(parsed.d).padStart(2, "0")}T00:00:00.000Z`;
    }
  }
  const compact = value.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (compact) return `${compact[1]}-${compact[2]}-${compact[3]}T00:00:00.000Z`;
  const iso = value.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (iso) return `${iso[1]}-${iso[2].padStart(2, "0")}-${iso[3].padStart(2, "0")}T00:00:00.000Z`;
  const dutch = value.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$/);
  if (dutch) return formatAmbiguousDate(dutch[1], dutch[2], dutch[3]);
  const shortDutch = value.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{2})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$/);
  if (shortDutch) return formatAmbiguousDate(shortDutch[1], shortDutch[2], `20${shortDutch[3]}`);
  return null;
}

function parseAmountCents(raw: Record<string, string>) {
  const combined = firstValue(raw, AMOUNT_KEYS);
  if (combined) {
    const cents = amountToCents(combined);
    const direction = firstValue(raw, DIRECTION_KEYS);
    if (cents !== null && direction && /^(af|debet|debit|d)$/i.test(direction.trim())) return -Math.abs(cents);
    if (cents !== null && direction && /^(bij|credit|creditering|c)$/i.test(direction.trim())) return Math.abs(cents);
    return cents;
  }
  const credit = firstValue(raw, CREDIT_KEYS);
  if (credit) return amountToCents(credit);
  const debit = firstValue(raw, DEBIT_KEYS);
  const debitCents = amountToCents(debit);
  return debitCents === null ? null : -Math.abs(debitCents);
}

function amountToCents(input: string | null) {
  if (!input) return null;
  const cleaned = input.replace(/\s/g, "").replace(/[€+]/g, "");
  const normalized = cleaned.includes(",") ? cleaned.replace(/\./g, "").replace(",", ".") : cleaned;
  const amount = Number(normalized);
  if (!Number.isFinite(amount)) return null;
  return Math.round(amount * 100);
}

function formatWorkbookCell(cell: string | number | boolean | Date | null) {
  if (cell instanceof Date) return cell.toISOString().slice(0, 10);
  if (typeof cell === "number") return String(cell);
  if (typeof cell === "boolean") return cell ? "true" : "false";
  return String(cell ?? "").trim();
}

function formatAmbiguousDate(first: string, second: string, year: string) {
  const a = Number(first);
  const b = Number(second);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const day = a > 12 ? a : b > 12 ? b : a;
  const month = a > 12 ? b : b > 12 ? a : b;
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}T00:00:00.000Z`;
}

function findMetaIban(rows: string[][]) {
  for (const row of rows) {
    const match = row.join(" ").match(/[A-Z]{2}\d{2}[A-Z0-9]{4}\d{10}/i);
    if (match) return match[0].replace(/\s+/g, "").toUpperCase();
  }
  return null;
}

function looksLikeIban(input: string) {
  return /^[A-Z]{2}\d{2}[A-Z0-9]{4}\d{10}$/i.test(input.replace(/\s+/g, ""));
}

function normalizeAccountIdentifier(input: string) {
  return input.replace(/\s+/g, "").toUpperCase();
}

function compact(input: string) {
  return input.replace(/\s+/g, " ").trim();
}

function stableTransactionId(parts: string[]) {
  let hash = 5381;
  for (const char of parts.join("|")) hash = (hash * 33) ^ char.charCodeAt(0);
  return `abn-manual-${(hash >>> 0).toString(16)}`;
}
