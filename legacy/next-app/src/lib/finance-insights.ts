import { dateKey, dateSortValue } from "@/lib/date-keys";
import type { AppData, FinanceItem } from "@/lib/types";

export type FinanceDashboardInsight = {
  today: string;
  monthlyByCategory: Record<string, number>;
  monthlyCommittedCents: number;
  dueWeekCents: number;
  dueMonthCents: number;
  overdueCount: number;
  dueWeekCount: number;
  dueMonthCount: number;
  unbudgetedCents: number;
  unbudgetedCount: number;
  budgetWarningCount: number;
  projectedBalanceCents: number | null;
  bankBalanceCents: number | null;
  recentIncomeCents: number;
  recentExpenseCents: number;
  recentNetCents: number;
  cashflowScore: number;
  signal: "urgent" | "attention" | "healthy" | "setup";
  signalTitle: string;
  signalDetail: string;
  nextPayment: FinanceItem | null;
};

export type RecurringCostInsight = {
  key: string;
  title: string;
  category: string | null;
  groupId: string | null;
  direction: "expense" | "income";
  cadence: "wekelijks" | "tweewekelijks" | "maandelijks" | "per kwartaal" | "jaarlijks" | "onregelmatig";
  confidence: "hoog" | "middel" | "laag";
  count: number;
  averageAmountCents: number;
  monthlyEstimateCents: number;
  lastAmountCents: number;
  lastDate: string;
  nextExpectedDate: string | null;
  accountIds: string[];
  forced: boolean;
};

export type RecurringCashflowTrendPoint = {
  month: string;
  label: string;
  incomeCents: number;
  expenseCents: number;
  netCents: number;
};

export function buildFinanceDashboardInsight(data: Pick<AppData, "financeItems" | "financeBudgets" | "bankAccounts" | "bankTransactions" | "bankConnections">, nowIso: string): FinanceDashboardInsight {
  const today = nowIso.slice(0, 10);
  const nextWeek = addDays(today, 7);
  const nextMonth = addDays(today, 30);
  const openItems = data.financeItems.filter((item) => item.status !== "betaald");
  const overdue = openItems.filter((item) => dateKey(item.due_date) !== null && dateKey(item.due_date)! < today);
  const dueWeek = openItems.filter((item) => isInRange(item.due_date, today, nextWeek));
  const dueMonth = openItems.filter((item) => isInRange(item.due_date, today, nextMonth));
  const monthlyByCategory = buildMonthlyByCategory(data.financeItems);
  const budgetWarnings = data.financeBudgets
    .map((budget) => {
      const spent = monthlyByCategory[budget.category] ?? 0;
      const ratio = budget.monthly_limit_cents > 0 ? spent / budget.monthly_limit_cents : 0;
      return { budget, spent, ratio };
    })
    .filter((item) => item.ratio >= Number(item.budget.alert_threshold));
  const unbudgeted = Object.entries(monthlyByCategory).filter(([category]) => !data.financeBudgets.some((budget) => budget.category === category));
  const bankBalances = data.bankAccounts
    .map((account) => account.balance_cents)
    .filter((balance): balance is number => balance !== null);
  const bankBalanceCents = bankBalances.length > 0 ? bankBalances.reduce((sum, amount) => sum + amount, 0) : null;
  const recentTransactions = data.bankTransactions.filter((transaction) => dateKey(transaction.booked_at) !== null && dateKey(transaction.booked_at)! >= addDays(today, -30));
  const recentIncomeCents = recentTransactions.filter((transaction) => transaction.amount_cents > 0).reduce((sum, item) => sum + item.amount_cents, 0);
  const recentExpenseCents = Math.abs(recentTransactions.filter((transaction) => transaction.amount_cents < 0).reduce((sum, item) => sum + item.amount_cents, 0));
  const dueMonthCents = dueMonth.reduce((sum, item) => sum + item.amount_cents, 0);
  const projectedBalanceCents = bankBalanceCents === null ? null : bankBalanceCents - dueMonthCents;
  const nextPayment = [...openItems].filter((item) => item.due_date).sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date))[0] ?? null;
  const monthlyCommittedCents = Object.values(monthlyByCategory).reduce((sum, amount) => sum + amount, 0);
  const cashflowScore = Math.min(
    100,
    overdue.length * 28 +
      budgetWarnings.length * 18 +
      unbudgeted.length * 8 +
      (projectedBalanceCents !== null && projectedBalanceCents < 0 ? 30 : 0) +
      (data.bankConnections.length === 0 ? 14 : 0),
  );
  const signal = getSignal({ overdueCount: overdue.length, budgetWarningCount: budgetWarnings.length, projectedBalanceCents, bankConnectionCount: data.bankConnections.length, cashflowScore });

  return {
    today,
    monthlyByCategory,
    monthlyCommittedCents,
    dueWeekCents: dueWeek.reduce((sum, item) => sum + item.amount_cents, 0),
    dueMonthCents,
    overdueCount: overdue.length,
    dueWeekCount: dueWeek.length,
    dueMonthCount: dueMonth.length,
    unbudgetedCents: unbudgeted.reduce((sum, [, amount]) => sum + amount, 0),
    unbudgetedCount: unbudgeted.length,
    budgetWarningCount: budgetWarnings.length,
    projectedBalanceCents,
    bankBalanceCents,
    recentIncomeCents,
    recentExpenseCents,
    recentNetCents: recentIncomeCents - recentExpenseCents,
    cashflowScore,
    signal,
    signalTitle: signalTitle(signal),
    signalDetail: signalDetail(signal, nextPayment, projectedBalanceCents),
    nextPayment,
  };
}

export function buildRecurringCostInsights(data: Pick<AppData, "bankTransactions"> & Partial<Pick<AppData, "recurringTransactionRules">>, nowIso: string, limit = 12): RecurringCostInsight[] {
  const today = nowIso.slice(0, 10);
  const groups = new Map<string, AppData["bankTransactions"]>();
  const rules = new Map((data.recurringTransactionRules ?? []).map((rule) => [rule.rule_key, rule]));

  for (const transaction of data.bankTransactions) {
    const date = dateKey(transaction.booked_at);
    if (!date || transaction.amount_cents === 0) continue;
    const identity = recurringIdentity(transaction.description);
    if (!identity.title || identity.title.length < 3) continue;
    const key = transaction.amount_cents > 0 ? `income:${identity.key}` : identity.key;
    groups.set(key, [...(groups.get(key) ?? []), transaction]);
  }

  return [...groups.entries()]
    .filter(([key]) => rules.get(key)?.action !== "exclude_recurring")
    .map(([key, transactions]) => buildRecurringGroupInsight(key, transactions, today, rules.get(key)?.action === "force_recurring", rules.get(key)?.group_id ?? null))
    .filter((item): item is RecurringCostInsight => Boolean(item))
    .sort((a, b) => {
      const confidenceScore = { hoog: 0, middel: 1, laag: 2 };
      return (
        Number(b.forced) - Number(a.forced) ||
        confidenceScore[a.confidence] - confidenceScore[b.confidence] ||
        b.count - a.count ||
        b.lastDate.localeCompare(a.lastDate) ||
        b.monthlyEstimateCents - a.monthlyEstimateCents
      );
    })
    .slice(0, limit);
}

export function buildRecurringCashflowTrend(data: Pick<AppData, "bankTransactions"> & Partial<Pick<AppData, "recurringTransactionRules">>, nowIso: string, months = 6): RecurringCashflowTrendPoint[] {
  const today = nowIso.slice(0, 10);
  const recurringKeys = new Set(buildRecurringCostInsights(data, nowIso, 250).map((item) => item.key));
  const monthKeys = recentMonthKeys(today, months);
  const points = new Map(
    monthKeys.map((month) => [
      month,
      {
        month,
        label: monthLabel(month),
        incomeCents: 0,
        expenseCents: 0,
        netCents: 0,
      },
    ]),
  );

  for (const transaction of data.bankTransactions) {
    const date = dateKey(transaction.booked_at);
    if (!date || date > today || transaction.amount_cents === 0) continue;
    const month = date.slice(0, 7);
    const point = points.get(month);
    if (!point) continue;
    const identity = recurringIdentity(transaction.description);
    const key = transaction.amount_cents > 0 ? `income:${identity.key}` : identity.key;
    if (!recurringKeys.has(key)) continue;
    if (transaction.amount_cents > 0) point.incomeCents += transaction.amount_cents;
    else point.expenseCents += Math.abs(transaction.amount_cents);
    point.netCents = point.incomeCents - point.expenseCents;
  }

  return monthKeys.map((month) => points.get(month)!);
}

export function recurringTransactionRuleIdentity(description: string) {
  const identity = recurringIdentity(description);
  return {
    ruleKey: identity.key,
    label: titleCase(identity.title),
  };
}

export function buildMonthlyByCategory(items: FinanceItem[]) {
  return items.reduce<Record<string, number>>((totals, item) => {
    if (item.status !== "actief") return totals;
    if (item.frequency === "eenmalig") return totals;
    const amount = item.frequency === "jaarlijks" ? Math.round(item.amount_cents / 12) : item.amount_cents;
    totals[item.category] = (totals[item.category] ?? 0) + amount;
    return totals;
  }, {});
}

function getSignal(input: { overdueCount: number; budgetWarningCount: number; projectedBalanceCents: number | null; bankConnectionCount: number; cashflowScore: number }): FinanceDashboardInsight["signal"] {
  if (input.overdueCount > 0 || (input.projectedBalanceCents !== null && input.projectedBalanceCents < 0)) return "urgent";
  if (input.budgetWarningCount > 0 || input.cashflowScore >= 35) return "attention";
  if (input.bankConnectionCount === 0) return "setup";
  return "healthy";
}

function signalTitle(signal: FinanceDashboardInsight["signal"]) {
  if (signal === "urgent") return "Nu controleren";
  if (signal === "attention") return "Let op deze maand";
  if (signal === "setup") return "Bankkoppeling mist";
  return "Financien rustig";
}

function signalDetail(signal: FinanceDashboardInsight["signal"], nextPayment: FinanceItem | null, projectedBalanceCents: number | null) {
  if (signal === "urgent" && projectedBalanceCents !== null && projectedBalanceCents < 0) return "De bekende bankbuffer wordt negatief na komende betaalmomenten.";
  if (signal === "urgent") return "Er zijn betaalmomenten die over tijd zijn.";
  if (signal === "attention") return nextPayment ? `Volgende betaling: ${nextPayment.title}` : "Budgetten of categorieen vragen aandacht.";
  if (signal === "setup") return "Koppel bunq om saldo, transacties en maandbuffer live te volgen.";
  return nextPayment ? `Volgende betaling: ${nextPayment.title}` : "Geen directe betaalactie gevonden.";
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function buildRecurringGroupInsight(key: string, transactions: AppData["bankTransactions"], today: string, forced = false, groupId: string | null = null): RecurringCostInsight | null {
  const sorted = [...transactions]
    .map((transaction) => ({ transaction, date: dateKey(transaction.booked_at) }))
    .filter((item): item is { transaction: AppData["bankTransactions"][number]; date: string } => Boolean(item.date))
    .sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return null;
  const direction = sorted.some((item) => item.transaction.amount_cents > 0) ? "income" : "expense";

  const intervals = sorted.slice(1).map((item, index) => daysBetween(sorted[index].date, item.date)).filter((days) => days > 0);
  const mandate = sorted.some((item) => isRecurringSepaMandate(item.transaction.description));
  const medianInterval = intervals.length > 0 ? median(intervals) : 30;
  const cadence = cadenceFromInterval(medianInterval) ?? (mandate || forced ? { label: "maandelijks" as const, monthlyFactor: 1 } : null);
  if (!cadence) return null;

  const amounts = sorted.map((item) => Math.abs(item.transaction.amount_cents));
  const averageAmountCents = direction === "income" ? conservativeRecurringIncomeAmount(amounts) : Math.round(median(amounts));
  const variance = averageAmountCents > 0 ? Math.max(...amounts.map((amount) => Math.abs(amount - averageAmountCents))) / averageAmountCents : 0;
  const intervalVariance = medianInterval > 0 ? Math.max(...intervals.map((interval) => Math.abs(interval - medianInterval))) / medianInterval : 0;
  const confidence = forced && sorted.length < 3 ? "middel" : mandate && sorted.length >= 4 ? "hoog" : mandate ? "middel" : sorted.length >= 4 && intervalVariance <= 0.25 ? "hoog" : sorted.length >= 3 && intervalVariance <= 0.45 ? "middel" : "laag";
  if (confidence === "laag" && sorted.length < 3) return null;

  const last = sorted[sorted.length - 1];
  const nextExpectedDate = addDays(last.date, Math.round(medianInterval));
  const activeEnough = nextExpectedDate >= addDays(today, -45);
  if (!activeEnough && !forced) return null;

  return {
    key,
    title: titleCase(recurringIdentity(sorted[sorted.length - 1].transaction.description).title),
    category: mostCommon(sorted.map((item) => item.transaction.category).filter((item): item is string => Boolean(item))),
    groupId,
    direction,
    cadence: cadence.label,
    confidence,
    count: sorted.length,
    averageAmountCents,
    monthlyEstimateCents: Math.round(averageAmountCents * cadence.monthlyFactor),
    lastAmountCents: Math.abs(last.transaction.amount_cents),
    lastDate: last.date,
    nextExpectedDate,
    accountIds: [...new Set(sorted.map((item) => item.transaction.account_id).filter((item): item is string => Boolean(item)))],
    forced,
  };
}

function recurringIdentity(description: string) {
  const sepa = parseSepaFields(description);
  const title = sepa.name ?? normalizeRecurringTitle(description);
  const mandateKey = sepa.mandate ? `:${sepa.mandate.toLowerCase()}` : "";
  const creditorKey = sepa.creditor ? `:${sepa.creditor.toLowerCase()}` : "";
  return {
    title,
    key: `${title.toLowerCase()}${creditorKey}${mandateKey}`,
  };
}

function recentMonthKeys(today: string, months: number) {
  const value = new Date(`${today.slice(0, 7)}-01T12:00:00.000Z`);
  value.setUTCMonth(value.getUTCMonth() - Math.max(0, months - 1));
  return Array.from({ length: months }, (_, index) => {
    const month = new Date(value);
    month.setUTCMonth(value.getUTCMonth() + index);
    return month.toISOString().slice(0, 7);
  });
}

function monthLabel(month: string) {
  const value = new Date(`${month}-01T12:00:00.000Z`);
  return new Intl.DateTimeFormat("nl-NL", { month: "short" }).format(value);
}

function conservativeRecurringIncomeAmount(amounts: number[]) {
  if (amounts.length === 0) return 0;
  const medianAmount = median(amounts);
  const regularAmounts = amounts.filter((amount) => amount >= medianAmount * 0.5);
  const baselineAmounts = regularAmounts.length >= 3 ? regularAmounts : amounts;
  const lowest = Math.min(...baselineAmounts);
  const recent = baselineAmounts.slice(-3);
  if (recent.length === 3 && recent.every((amount) => amount > lowest) && isStableHigherIncomeRun(recent)) return Math.round(median(recent));
  return lowest;
}

function isStableHigherIncomeRun(amounts: number[]) {
  const baseline = median(amounts);
  if (baseline <= 0) return false;
  return Math.max(...amounts.map((amount) => Math.abs(amount - baseline))) / baseline <= 0.1;
}

function normalizeRecurringTitle(description: string) {
  return description
    .replace(/\bBEA,\s*/gi, "")
    .replace(/\bApple Pay\s+/gi, "")
    .replace(/\bTRTP\/[^/]*(?=\/|$)/gi, "")
    .replace(/\/(?:CSID|MARF|REMI|EREF|IBAN|BIC|RTRN|PURP)\/[^/]*(?=\/[A-Z]{2,5}\/|$)/gi, "")
    .replace(/\/NAME\/([^/]+).*/i, "$1")
    .replace(/,?\s*PAS\s*[A-Z0-9]{2,}\b/gi, "")
    .replace(/\bPAS[A-Z0-9]{2,}\b/gi, "")
    .replace(/\b(?:NR|TRANSACTIENR|TRANSACTIENUMMER|KENMERK)[:\s]*[A-Z0-9-]{3,}\b/gi, "")
    .replace(/,?\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\/\d{1,2}:\d{2}\s+[A-Z][A-Z\s.'-]{2,}\b/g, "")
    .replace(/[0-9]{4,}/g, "")
    .replace(/[^a-zA-ZÀ-ÿ0-9&.' -]+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function isRecurringSepaMandate(description: string) {
  const upper = description.toUpperCase();
  const sepa = parseSepaFields(description);
  return upper.includes("SEPA") && Boolean(sepa.mandate) && /(DOORLOPEND|ALGEMEEN|INCASSO)/.test(upper);
}

function parseSepaFields(description: string) {
  return {
    name: parseSlashField(description, "NAME") ?? parseTextField(description, ["Naam"]),
    mandate: parseSlashField(description, "MARF") ?? parseTextField(description, ["Machtiging"]),
    creditor: parseSlashField(description, "CSID") ?? parseTextField(description, ["Incassant"]),
  };
}

function parseSlashField(input: string, key: string) {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = input.match(new RegExp(`/${escaped}/([^/]*?)(?=/[A-Z]{2,5}/|$)`, "i"));
  return match?.[1]?.trim() || null;
}

function parseTextField(input: string, labels: string[]) {
  for (const label of labels) {
    const match = input.match(new RegExp(`${label}:\\s*(.*?)(?=\\s+(?:Incassant|Naam|Machtiging|Omschrijving|IBAN|Kenmerk):|$)`, "i"));
    if (match?.[1]?.trim()) return match[1].trim();
  }
  return null;
}

function cadenceFromInterval(days: number): { label: RecurringCostInsight["cadence"]; monthlyFactor: number } | null {
  if (days >= 5 && days <= 9) return { label: "wekelijks", monthlyFactor: 52 / 12 };
  if (days >= 12 && days <= 17) return { label: "tweewekelijks", monthlyFactor: 26 / 12 };
  if (days >= 25 && days <= 38) return { label: "maandelijks", monthlyFactor: 1 };
  if (days >= 80 && days <= 100) return { label: "per kwartaal", monthlyFactor: 1 / 3 };
  if (days >= 330 && days <= 400) return { label: "jaarlijks", monthlyFactor: 1 / 12 };
  return null;
}

function daysBetween(start: string, end: string) {
  return Math.round((Date.parse(`${end}T12:00:00.000Z`) - Date.parse(`${start}T12:00:00.000Z`)) / 86_400_000);
}

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function mostCommon(values: string[]) {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}

function titleCase(input: string) {
  return input
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function isInRange(value: string | Date | null, start: string, end: string) {
  const key = dateKey(value);
  return key !== null && key >= start && key <= end;
}
