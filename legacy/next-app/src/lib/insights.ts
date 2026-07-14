import { dateKey } from "@/lib/date-keys";
import { money, shortDate } from "@/lib/format";
import type { AppData } from "@/lib/types";

export type FamilyInsight = {
  id: string;
  title: string;
  detail: string;
  href: string;
  tone: "urgent" | "attention" | "info";
};

const recurrenceDays: Record<string, number> = {
  weekly: 7,
  biweekly: 14,
  monthly: 30,
};

export function buildFamilyInsights(data: AppData, nowIso: string): FamilyInsight[] {
  const now = new Date(nowIso);
  const today = nowIso.slice(0, 10);
  const tomorrow = addDays(today, 1);
  const nextWeek = addDays(today, 7);
  const insights: FamilyInsight[] = [];

  const mainTasks = data.tasks.filter((task) => !task.parent_task_id);
  const overdueTasks = mainTasks.filter((task) => task.status === "open" && dateKey(task.due_date) !== null && dateKey(task.due_date)! < today);
  if (overdueTasks.length > 0) {
    insights.push({
      id: "tasks-overdue",
      title: `${overdueTasks.length} taak${overdueTasks.length === 1 ? "" : "en"} te laat`,
      detail: overdueTasks[0]?.title ?? "Bekijk open taken",
      href: "/taken?filter=open",
      tone: "urgent",
    });
  }

  const dueToday = mainTasks.filter((task) => task.status === "open" && dateKey(task.due_date) === today);
  if (dueToday.length > 0) {
    insights.push({
      id: "tasks-today",
      title: `${dueToday.length} taak${dueToday.length === 1 ? "" : "en"} vandaag`,
      detail: dueToday.map((task) => task.title).slice(0, 2).join(", "),
      href: "/taken?filter=vandaag",
      tone: "attention",
    });
  }

  const pinnedNotes = data.householdNotes.filter((note) => note.pinned);
  if (pinnedNotes.length > 0) {
    insights.push({
      id: "notes-pinned",
      title: `${pinnedNotes.length} vastgezet bericht${pinnedNotes.length === 1 ? "" : "en"}`,
      detail: pinnedNotes[0]?.title ?? "Bekijk prikbord",
      href: "/prikbord",
      tone: "info",
    });
  }

  const overdueMaintenance = data.maintenanceItems.filter((item) => item.status === "open" && dateKey(item.due_date) !== null && dateKey(item.due_date)! < today);
  if (overdueMaintenance.length > 0) {
    insights.push({
      id: "maintenance-overdue",
      title: `${overdueMaintenance.length} onderhoudstaak${overdueMaintenance.length === 1 ? "" : "en"} te laat`,
      detail: overdueMaintenance[0]?.title ?? "Bekijk onderhoud",
      href: "/onderhoud",
      tone: "urgent",
    });
  }

  const maintenanceSoon = data.maintenanceItems.filter((item) => item.status === "open" && isInRange(item.due_date, today, nextWeek));
  if (maintenanceSoon.length > 0) {
    insights.push({
      id: "maintenance-soon",
      title: `${maintenanceSoon.length} onderhoudstaak${maintenanceSoon.length === 1 ? "" : "en"} deze week`,
      detail: maintenanceSoon.slice(0, 2).map((item) => item.title).join(", "),
      href: "/onderhoud",
      tone: "attention",
    });
  }

  const nextMonth = addDays(today, 30);
  const expiringDocuments = data.householdDocuments.filter((document) => isInRange(document.expires_at, today, nextMonth));
  if (expiringDocuments.length > 0) {
    insights.push({
      id: "documents-expiring",
      title: `${expiringDocuments.length} document${expiringDocuments.length === 1 ? "" : "en"} verlopen binnenkort`,
      detail: expiringDocuments.slice(0, 2).map((document) => document.title).join(", "),
      href: "/documenten",
      tone: "attention",
    });
  }

  const openShopping = data.shoppingItems.filter((item) => !item.checked);
  if (openShopping.length > 0) {
    insights.push({
      id: "shopping-open",
      title: `${openShopping.length} boodschap${openShopping.length === 1 ? "" : "pen"} open`,
      detail: openShopping.slice(0, 3).map((item) => item.name).join(", "),
      href: "/boodschappen",
      tone: "info",
    });
  }

  const mealsToday = data.mealPlans.filter((meal) => dateKey(meal.planned_date as string | Date) === today);
  if (mealsToday.length > 0) {
    insights.push({
      id: "meals-today",
      title: `${mealsToday.length} maaltijd${mealsToday.length === 1 ? "" : "en"} vandaag`,
      detail: mealsToday.map((meal) => meal.title).slice(0, 2).join(", "),
      href: "/boodschappen?tab=maaltijden",
      tone: "info",
    });
  }

  const recurringDue = data.shoppingProducts.filter((product) => {
    const interval = recurrenceDays[product.recurrence];
    if (!interval) return false;
    if (!product.last_purchased_at) return true;
    return daysBetween(new Date(product.last_purchased_at), now) >= interval;
  });
  if (recurringDue.length > 0) {
    insights.push({
      id: "shopping-recurring",
      title: "Terugkerende producten",
      detail: recurringDue.slice(0, 3).map((product) => product.name).join(", "),
      href: "/boodschappen",
      tone: "attention",
    });
  }

  const financeDue = data.financeItems.filter((item) => item.status !== "betaald" && isInRange(item.due_date, today, nextWeek));
  if (financeDue.length > 0) {
    const total = financeDue.reduce((sum, item) => sum + item.amount_cents, 0);
    insights.push({
      id: "finance-due",
      title: `${financeDue.length} betaalmoment${financeDue.length === 1 ? "" : "en"} deze week`,
      detail: `${money(total)} gepland`,
      href: "/geld",
      tone: "attention",
    });
  }

  const monthlyByCategory = data.financeItems.reduce<Record<string, number>>((totals, item) => {
    if (item.status !== "actief" || item.frequency === "eenmalig") return totals;
    const amount = item.frequency === "jaarlijks" ? Math.round(item.amount_cents / 12) : item.amount_cents;
    totals[item.category] = (totals[item.category] ?? 0) + amount;
    return totals;
  }, {});
  const budgetWarnings = data.financeBudgets
    .map((budget) => {
      const spent = monthlyByCategory[budget.category] ?? 0;
      const ratio = budget.monthly_limit_cents > 0 ? spent / budget.monthly_limit_cents : 0;
      return { budget, spent, ratio };
    })
    .filter((item) => item.ratio >= Number(item.budget.alert_threshold))
    .sort((a, b) => b.ratio - a.ratio);
  if (budgetWarnings.length > 0) {
    const warning = budgetWarnings[0];
    insights.push({
      id: "finance-budget-warning",
      title: `${warning.budget.category} bijna op budget`,
      detail: `${money(warning.spent)} van ${money(warning.budget.monthly_limit_cents)} gebruikt`,
      href: "/geld",
      tone: warning.ratio >= 1 ? "urgent" : "attention",
    });
  }

  const unbudgetedCategories = Object.keys(monthlyByCategory).filter(
    (category) => !data.financeBudgets.some((budget) => budget.category === category),
  );
  if (unbudgetedCategories.length > 0) {
    insights.push({
      id: "finance-unbudgeted",
      title: "Vaste lasten zonder budget",
      detail: unbudgetedCategories.slice(0, 3).join(", "),
      href: "/geld",
      tone: "info",
    });
  }

  const eventsToday = data.calendarEvents.filter((event) => dateKey(event.starts_at) === today);
  const eventsTomorrow = data.calendarEvents.filter((event) => dateKey(event.starts_at) === tomorrow);
  if (eventsToday.length > 0 || eventsTomorrow.length > 0) {
    const events = eventsToday.length > 0 ? eventsToday : eventsTomorrow;
    insights.push({
      id: eventsToday.length > 0 ? "events-today" : "events-tomorrow",
      title: eventsToday.length > 0 ? `${eventsToday.length} afspraak vandaag` : `${eventsTomorrow.length} afspraak morgen`,
      detail: `${events[0]?.title ?? "Afspraak"} · ${shortDate(events[0]?.starts_at ?? null)}`,
      href: "/agenda",
      tone: eventsToday.length > 0 ? "attention" : "info",
    });
  }

  if (data.calendarIntegrations.length === 0) {
    insights.push({
      id: "setup-calendar",
      title: "Outlook agenda nog niet gekoppeld",
      detail: "Koppel gezinsagenda's voor een volledig dagoverzicht.",
      href: "/instellingen",
      tone: "info",
    });
  }

  if (data.householdContacts.length === 0) {
    insights.push({
      id: "setup-contacts",
      title: "Belangrijke contacten ontbreken",
      detail: "Voeg huisarts, school, buren of noodcontacten toe.",
      href: "/gezin",
      tone: "info",
    });
  }

  if (data.bankConnections.length === 0) {
    insights.push({
      id: "setup-bank",
      title: "Bankkoppeling nog niet actief",
      detail: "Voeg bunq toe om vaste lasten en transacties rijker te maken.",
      href: "/geld",
      tone: "info",
    });
  }

  if (!data.hasHomeAssistantConfig && !data.hasHueConfig) {
    insights.push({
      id: "setup-home",
      title: "Smart home nog niet gekoppeld",
      detail: "Koppel Hue of Home Assistant voor bediening vanuit de app.",
      href: "/home",
      tone: "info",
    });
  }

  return insights.sort((a, b) => toneScore(a.tone) - toneScore(b.tone)).slice(0, 7);
}

function toneScore(tone: FamilyInsight["tone"]) {
  if (tone === "urgent") return 0;
  if (tone === "attention") return 1;
  return 2;
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T00:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function isInRange(value: string | Date | null, start: string, end: string) {
  const key = dateKey(value);
  return key !== null && key >= start && key <= end;
}

function daysBetween(start: Date, end: Date) {
  return Math.floor((end.getTime() - start.getTime()) / 86_400_000);
}
