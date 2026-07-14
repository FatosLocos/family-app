import { money, shortDate } from "@/lib/format";
import type { AppData } from "@/lib/types";

export type SearchResult = {
  id: string;
  module: string;
  title: string;
  detail: string;
  href: string;
  meta: string;
  privacy: "normal" | "masked";
  matchText: string;
};

export function buildSearchResults(data: AppData, query: string): SearchResult[] {
  const normalizedQuery = normalize(query);
  if (normalizedQuery.length < 2) return [];

  const results: SearchResult[] = [
    ...data.householdNotes.map((note) => ({
      id: `note-${note.id}`,
      module: "Prikbord",
      title: note.title,
      detail: [note.category, note.body].filter(Boolean).join(" · "),
      href: "/prikbord",
      meta: [note.category, note.pinned ? "Vastgezet" : ""].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [note.category, note.body].filter(Boolean).join(" "),
    })),
    ...data.tasks.map((task) => ({
      id: `task-${task.id}`,
      module: "Taken",
      title: task.title,
      detail: [task.priority, task.status, shortDate(task.due_date), task.description].filter(Boolean).join(" · "),
      href: "/taken?filter=alles",
      meta: [task.status === "done" ? "Afgerond" : "Open", task.priority, shortDate(task.due_date)].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [task.priority, task.status, shortDate(task.due_date), task.description].filter(Boolean).join(" "),
    })),
    ...data.shoppingItems.map((item) => ({
      id: `shopping-${item.id}`,
      module: "Boodschappen",
      title: item.name,
      detail: [item.category, item.quantity, item.checked ? "Afgevinkt" : "Open"].filter(Boolean).join(" · "),
      href: "/boodschappen",
      meta: [item.checked ? "Afgevinkt" : "Open", item.category].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [item.category, item.quantity, item.checked ? "Afgevinkt" : "Open"].filter(Boolean).join(" "),
    })),
    ...data.mealPlans.map((meal) => ({
      id: `meal-${meal.id}`,
      module: "Maaltijden",
      title: meal.title,
      detail: [meal.meal_type, shortDate(meal.planned_date), meal.ingredients, meal.notes].filter(Boolean).join(" · "),
      href: "/boodschappen?tab=maaltijden",
      meta: [meal.meal_type, shortDate(meal.planned_date)].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [meal.meal_type, shortDate(meal.planned_date), meal.ingredients, meal.notes].filter(Boolean).join(" "),
    })),
    ...data.financeItems.map((item) => ({
      id: `finance-${item.id}`,
      module: "Geld",
      title: item.title,
      detail: [item.category, item.frequency, money(item.amount_cents), shortDate(item.due_date)].filter(Boolean).join(" · "),
      href: "/geld",
      meta: [item.status, money(item.amount_cents), shortDate(item.due_date)].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [item.category, item.frequency, money(item.amount_cents), shortDate(item.due_date)].filter(Boolean).join(" "),
    })),
    ...data.calendarEvents.map((event) => ({
      id: `event-${event.id}`,
      module: "Agenda",
      title: event.title,
      detail: [shortDate(event.starts_at), event.location, event.external_calendar_name].filter(Boolean).join(" · "),
      href: "/agenda",
      meta: [shortDate(event.starts_at), event.source_provider === "outlook" ? "Outlook" : event.source_provider === "ics" ? "ICS agenda" : ""].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [shortDate(event.starts_at), event.location, event.external_calendar_name].filter(Boolean).join(" "),
    })),
    ...data.householdContacts.map((contact) => ({
      id: `contact-${contact.id}`,
      module: "Gezin",
      title: contact.name,
      detail: [contact.relationship, contact.phone, contact.email, contact.address, contact.notes].filter(Boolean).join(" · "),
      href: "/gezin",
      meta: [contact.relationship, contact.priority].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [contact.relationship, contact.phone, contact.email, contact.address, contact.notes].filter(Boolean).join(" "),
    })),
    ...data.householdDocuments.map((document) => ({
      id: `document-${document.id}`,
      module: "Documenten",
      title: document.title,
      detail: [
        document.category,
        document.owner_name,
        document.location,
        document.is_sensitive ? "Gevoelige referentie verborgen" : document.reference,
        shortDate(document.expires_at),
        document.notes,
      ]
        .filter(Boolean)
        .join(" · "),
      href: "/documenten",
      meta: [document.category, document.is_sensitive ? "Gevoelig" : "", shortDate(document.expires_at)].filter(Boolean).join(" · "),
      privacy: document.is_sensitive ? "masked" as const : "normal" as const,
      matchText: [
        document.category,
        document.owner_name,
        document.location,
        document.is_sensitive ? "gevoelig afgeschermd" : document.reference,
        shortDate(document.expires_at),
        document.notes,
      ].filter(Boolean).join(" "),
    })),
    ...data.maintenanceItems.map((item) => ({
      id: `maintenance-${item.id}`,
      module: "Onderhoud",
      title: item.title,
      detail: [item.area, item.provider, item.frequency, item.status, shortDate(item.due_date), item.notes].filter(Boolean).join(" · "),
      href: "/onderhoud",
      meta: [item.status === "done" ? "Afgerond" : "Open", item.area, shortDate(item.due_date)].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [item.area, item.provider, item.frequency, item.status, shortDate(item.due_date), item.notes].filter(Boolean).join(" "),
    })),
    ...data.householdInfoItems.map((item) => ({
      id: `info-${item.id}`,
      module: "Huisinfo",
      title: item.title,
      detail: [item.category, item.is_sensitive ? "Gevoelige waarde verborgen" : item.value, item.notes].filter(Boolean).join(" · "),
      href: "/gezin",
      meta: [item.category, item.is_sensitive ? "Gevoelig" : ""].filter(Boolean).join(" · "),
      privacy: item.is_sensitive ? "masked" as const : "normal" as const,
      matchText: [item.category, item.is_sensitive ? "gevoelig afgeschermd" : item.value, item.notes].filter(Boolean).join(" "),
    })),
    ...data.wishlistItems.map((item) => ({
      id: `wishlist-${item.id}`,
      module: "Wishlist",
      title: item.title,
      detail: [item.desired_by, item.category, item.description, item.url].filter(Boolean).join(" · "),
      href: "/wishlist",
      meta: [wishlistStatusLabel(item.status), item.is_public ? "Extern zichtbaar" : "Prive", item.price_cents ? money(item.price_cents) : null].filter(Boolean).join(" · "),
      privacy: "normal" as const,
      matchText: [item.desired_by, item.category, item.description, item.status, item.url].filter(Boolean).join(" "),
    })),
  ];

  return results
    .filter((result) => normalize([result.module, result.title, result.meta, result.matchText].join(" ")).includes(normalizedQuery))
    .slice(0, 50);
}

function wishlistStatusLabel(status: string) {
  if (status === "reserved") return "Gereserveerd";
  if (status === "purchased") return "Afgestreept";
  return "Open";
}

function normalize(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}
