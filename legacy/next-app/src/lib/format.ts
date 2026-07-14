export function money(cents: number) {
  return new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(cents / 100);
}

export function shortDate(value: string | Date | null) {
  if (!value) return "Geen datum";
  const hasTime = typeof value === "string" ? value.includes("T") : value.getHours() + value.getMinutes() + value.getSeconds() > 0;
  return new Intl.DateTimeFormat("nl-NL", { dateStyle: "medium", timeStyle: hasTime ? "short" : undefined }).format(new Date(value));
}

export function memberName(userId: string | null, members: { user_id: string; profile?: { full_name: string | null; email: string | null } | null }[]) {
  if (!userId) return "Niet toegewezen";
  const member = members.find((item) => item.user_id === userId);
  return member?.profile?.full_name ?? member?.profile?.email ?? "Gezinslid";
}
