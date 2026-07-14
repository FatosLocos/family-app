import { dateKey } from "@/lib/date-keys";
import { money, shortDate } from "@/lib/format";
import type { AppData } from "@/lib/types";

export type NotificationItem = {
  id: string;
  module: "Taken" | "Agenda" | "Boodschappen" | "Geld" | "Documenten" | "Onderhoud" | "Prikbord" | "Instellingen";
  title: string;
  detail: string;
  href: string;
  tone: "urgent" | "attention" | "info";
  dueLabel: string;
};

const recurrenceDays: Record<string, number> = {
  weekly: 7,
  biweekly: 14,
  monthly: 30,
};

export function buildNotifications(data: AppData, nowIso: string): NotificationItem[] {
  const now = new Date(nowIso);
  const today = nowIso.slice(0, 10);
  const tomorrow = addDays(today, 1);
  const nextWeek = addDays(today, 7);
  const nextMonth = addDays(today, 30);
  const notifications: NotificationItem[] = [];

  data.tasks
    .filter((task) => !task.parent_task_id && task.status === "open" && isDueBy(task.due_date, tomorrow))
    .forEach((task) => {
      const due = dateKey(task.due_date);
      notifications.push({
        id: `task-${task.id}`,
        module: "Taken",
        title: task.title,
        detail: [task.priority, task.description].filter(Boolean).join(" · ") || "Open taak",
        href: due === today ? "/taken?filter=vandaag" : "/taken?filter=open",
        tone: due !== null && due < today ? "urgent" : "attention",
        dueLabel: dateLabel(task.due_date, today, tomorrow),
      });
    });

  data.calendarEvents
    .filter((event) => isInRange(event.starts_at, today, tomorrow))
    .forEach((event) => {
      const start = dateKey(event.starts_at);
      notifications.push({
        id: `event-${event.id}`,
        module: "Agenda",
        title: event.title,
        detail: [shortDate(event.starts_at), event.location, event.external_calendar_name].filter(Boolean).join(" · "),
        href: "/agenda",
        tone: start === today ? "attention" : "info",
        dueLabel: dateLabel(event.starts_at, today, tomorrow),
      });
    });

  data.maintenanceItems
    .filter((item) => item.status === "open" && isDueBy(item.due_date, nextWeek))
    .forEach((item) => {
      const due = dateKey(item.due_date);
      notifications.push({
        id: `maintenance-${item.id}`,
        module: "Onderhoud",
        title: item.title,
        detail: [item.area, item.provider, item.notes].filter(Boolean).join(" · ") || "Huisonderhoud",
        href: "/onderhoud",
        tone: due !== null && due < today ? "urgent" : "attention",
        dueLabel: dateLabel(item.due_date, today, tomorrow),
      });
    });

  data.financeItems
    .filter((item) => item.status !== "betaald" && isDueBy(item.due_date, nextWeek))
    .forEach((item) => {
      const due = dateKey(item.due_date);
      notifications.push({
        id: `finance-${item.id}`,
        module: "Geld",
        title: item.title,
        detail: `${item.category} · ${money(item.amount_cents)} · ${item.frequency}`,
        href: "/geld",
        tone: due !== null && due < today ? "urgent" : "attention",
        dueLabel: dateLabel(item.due_date, today, tomorrow),
      });
    });

  data.householdDocuments
    .filter((document) => isDueBy(document.expires_at, nextMonth))
    .forEach((document) => {
      const expiry = dateKey(document.expires_at);
      notifications.push({
        id: `document-${document.id}`,
        module: "Documenten",
        title: document.title,
        detail: [document.category, document.owner_name, document.location].filter(Boolean).join(" · ") || "Document",
        href: "/documenten",
        tone: expiry !== null && expiry < today ? "urgent" : "attention",
        dueLabel: document.expires_at ? `Vervalt ${dateLabel(document.expires_at, today, tomorrow).toLowerCase()}` : "Geen datum",
      });
    });

  data.shoppingProducts
    .filter((product) => {
      const interval = recurrenceDays[product.recurrence];
      if (!interval) return false;
      if (!product.last_purchased_at) return true;
      return daysBetween(new Date(product.last_purchased_at), now) >= interval;
    })
    .forEach((product) => {
      notifications.push({
        id: `shopping-product-${product.id}`,
        module: "Boodschappen",
        title: product.name,
        detail: [product.category, product.default_quantity, recurrenceLabel(product.recurrence)].filter(Boolean).join(" · "),
        href: "/boodschappen",
        tone: "attention",
        dueLabel: "Terugkerend",
      });
    });

  data.householdNotes
    .filter((note) => note.pinned)
    .slice(0, 5)
    .forEach((note) => {
      notifications.push({
        id: `note-${note.id}`,
        module: "Prikbord",
        title: note.title,
        detail: note.body,
        href: "/prikbord",
        tone: "info",
        dueLabel: "Vastgezet",
      });
    });

  if (data.calendarIntegrations.length === 0) {
    notifications.push({
      id: "setup-calendar",
      module: "Instellingen",
      title: "Outlook agenda nog niet gekoppeld",
      detail: "Koppel gezinsagenda's voor een volledig dagoverzicht.",
      href: "/instellingen",
      tone: "info",
      dueLabel: "Setup",
    });
  }

  return notifications.sort((a, b) => toneScore(a.tone) - toneScore(b.tone) || a.module.localeCompare(b.module));
}

function toneScore(tone: NotificationItem["tone"]) {
  if (tone === "urgent") return 0;
  if (tone === "attention") return 1;
  return 2;
}

function dateLabel(value: string | Date | null, today: string, tomorrow: string) {
  const key = dateKey(value);
  if (!key) return "Geen datum";
  if (key < today) return "Te laat";
  if (key === today) return "Vandaag";
  if (key === tomorrow) return "Morgen";
  return shortDate(value);
}

function isDueBy(value: string | Date | null, end: string) {
  const key = dateKey(value);
  return key !== null && key <= end;
}

function isInRange(value: string | Date | null, start: string, end: string) {
  const key = dateKey(value);
  return key !== null && key >= start && key <= end;
}

function recurrenceLabel(recurrence: string) {
  if (recurrence === "weekly") return "Wekelijks";
  if (recurrence === "biweekly") return "Elke twee weken";
  if (recurrence === "monthly") return "Maandelijks";
  return "Terugkerend";
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T00:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function daysBetween(start: Date, end: Date) {
  return Math.floor((end.getTime() - start.getTime()) / 86_400_000);
}
