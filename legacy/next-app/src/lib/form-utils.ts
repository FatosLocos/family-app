export function formValue(formData: FormData, key: string) {
  const raw = formData.get(key);
  return typeof raw === "string" && raw.trim() ? raw.trim() : null;
}

export function centsFromEuros(input: string | null) {
  if (!input) return null;
  const normalized = input.replace(",", ".");
  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return Math.round(amount * 100);
}

export function centsFromText(input: string | null) {
  if (!input) return null;
  const normalized = input.replace(/\s+/g, " ");
  const match = normalized.match(/(?:€\s*)?(\d+(?:[.,]\d{1,2})?)/);
  return centsFromEuros(match?.[1] ?? null);
}

export function internalRedirectPath(input: string | null) {
  if (!input || !input.startsWith("/") || input.startsWith("//")) return "/";
  return input;
}
