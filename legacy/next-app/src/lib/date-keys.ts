export type DateLike = string | Date | null | undefined;

export function dateKey(value: DateLike) {
  if (!value) return null;
  if (value instanceof Date) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  return value.slice(0, 10);
}

export function dateSortValue(value: DateLike) {
  const key = dateKey(value);
  if (!key) return Number.MAX_SAFE_INTEGER;
  return new Date(`${key}T12:00:00.000Z`).getTime();
}
