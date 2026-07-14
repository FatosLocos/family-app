import { money, shortDate } from "@/lib/format";
import type { AppData } from "@/lib/types";

export type ActivityItem = {
  id: string;
  module: string;
  title: string;
  detail: string;
  at: string;
  href: string;
  tone: "neutral" | "success" | "attention" | "urgent";
  timing: "recent" | "upcoming";
};

export function buildActivityFeed(data: AppData, nowInput: string, limit = 40) {
  const now = new Date(nowInput).getTime();
  const startOfToday = new Date(nowInput.slice(0, 10)).getTime();
  const items: ActivityItem[] = [];

  for (const task of data.tasks) {
    if (task.completed_at) {
      items.push({
        id: `task-done-${task.id}`,
        module: "Taken",
        title: "Taak afgerond",
        detail: task.title,
        at: task.completed_at,
        href: "/taken",
        tone: "success",
        timing: "recent",
      });
    } else if (task.due_date) {
      const dueTime = new Date(task.due_date).getTime();
      items.push({
        id: `task-due-${task.id}`,
        module: "Taken",
        title: dueTime < startOfToday ? "Taak over tijd" : "Taak gepland",
        detail: `${task.title} · ${shortDate(task.due_date)}`,
        at: task.due_date,
        href: "/taken",
        tone: dueTime < startOfToday ? "urgent" : "attention",
        timing: dueTime < startOfToday ? "recent" : "upcoming",
      });
    } else if (task.created_at) {
      items.push({
        id: `task-created-${task.id}`,
        module: "Taken",
        title: "Taak toegevoegd",
        detail: task.title,
        at: task.created_at,
        href: "/taken",
        tone: "neutral",
        timing: "recent",
      });
    }
  }

  for (const item of data.shoppingItems) {
    if (!item.created_at) continue;
    items.push({
      id: `shopping-${item.id}`,
      module: "Boodschappen",
      title: item.checked ? "Boodschap afgevinkt" : "Boodschap toegevoegd",
      detail: [item.name, item.quantity, item.category].filter(Boolean).join(" · "),
      at: item.created_at,
      href: "/boodschappen",
      tone: item.checked ? "success" : "neutral",
      timing: "recent",
    });
  }

  for (const note of data.householdNotes) {
    items.push({
      id: `note-${note.id}`,
      module: "Prikbord",
      title: note.pinned ? "Bericht vastgezet" : "Bericht geplaatst",
      detail: note.title,
      at: note.created_at,
      href: "/prikbord",
      tone: note.pinned ? "attention" : "neutral",
      timing: "recent",
    });
  }

  for (const event of data.calendarEvents) {
    const start = new Date(event.starts_at).getTime();
    items.push({
      id: `event-${event.id}`,
      module: "Agenda",
      title: start >= now ? "Afspraak gepland" : "Afspraak geweest",
      detail: `${event.title} · ${shortDate(event.starts_at)}`,
      at: event.starts_at,
      href: "/agenda",
      tone: start >= now ? "attention" : "neutral",
      timing: start >= now ? "upcoming" : "recent",
    });
  }

  for (const meal of data.mealPlans) {
    const planned = new Date(meal.planned_date).getTime();
    items.push({
      id: `meal-${meal.id}`,
      module: "Maaltijden",
      title: planned >= startOfToday ? "Maaltijd gepland" : "Maaltijd geweest",
      detail: `${meal.title} · ${meal.meal_type} · ${shortDate(meal.planned_date)}`,
      at: meal.planned_date,
      href: "/boodschappen?tab=maaltijden",
      tone: planned >= startOfToday ? "attention" : "neutral",
      timing: planned >= startOfToday ? "upcoming" : "recent",
    });
  }

  for (const item of data.financeItems) {
    if (!item.due_date) continue;
    const due = new Date(item.due_date).getTime();
    items.push({
      id: `finance-${item.id}`,
      module: "Geld",
      title: due < startOfToday && item.status !== "betaald" ? "Betaalmoment over tijd" : "Betaalmoment",
      detail: `${item.title} · ${money(item.amount_cents)} · ${shortDate(item.due_date)}`,
      at: item.due_date,
      href: "/geld",
      tone: due < startOfToday && item.status !== "betaald" ? "urgent" : "attention",
      timing: due < startOfToday ? "recent" : "upcoming",
    });
  }

  for (const item of data.maintenanceItems) {
    if (item.completed_at) {
      items.push({
        id: `maintenance-done-${item.id}`,
        module: "Onderhoud",
        title: "Onderhoud afgerond",
        detail: item.title,
        at: item.completed_at,
        href: "/onderhoud",
        tone: "success",
        timing: "recent",
      });
    } else if (item.due_date) {
      const due = new Date(item.due_date).getTime();
      items.push({
        id: `maintenance-due-${item.id}`,
        module: "Onderhoud",
        title: due < startOfToday ? "Onderhoud over tijd" : "Onderhoud gepland",
        detail: `${item.title} · ${shortDate(item.due_date)}`,
        at: item.due_date,
        href: "/onderhoud",
        tone: due < startOfToday ? "urgent" : "attention",
        timing: due < startOfToday ? "recent" : "upcoming",
      });
    }
  }

  for (const document of data.householdDocuments) {
    if (document.created_at) {
      items.push({
        id: `document-created-${document.id}`,
        module: "Documenten",
        title: "Document toegevoegd",
        detail: document.title,
        at: document.created_at,
        href: "/documenten",
        tone: document.is_sensitive ? "attention" : "neutral",
        timing: "recent",
      });
    }
    if (document.expires_at) {
      const expires = new Date(document.expires_at).getTime();
      items.push({
        id: `document-expires-${document.id}`,
        module: "Documenten",
        title: expires < startOfToday ? "Document verlopen" : "Document verloopt",
        detail: `${document.title} · ${shortDate(document.expires_at)}`,
        at: document.expires_at,
        href: "/documenten",
        tone: expires < startOfToday ? "urgent" : "attention",
        timing: expires < startOfToday ? "recent" : "upcoming",
      });
    }
  }

  for (const observation of data.priceObservations) {
    items.push({
      id: `price-${observation.id}`,
      module: "Boodschappen",
      title: "Prijs opgeslagen",
      detail: `${observation.product_name} · ${money(observation.total_price_cents)}${observation.store ? ` · ${observation.store}` : ""}`,
      at: observation.observed_at,
      href: "/boodschappen",
      tone: "neutral",
      timing: "recent",
    });
  }

  for (const scan of data.shoppingScans) {
    items.push({
      id: `scan-${scan.id}`,
      module: "Boodschappen",
      title: scan.status === "failed" ? "Bon-scan mislukt" : "Bon-scan verwerkt",
      detail: scan.source_filename ?? "Boodschappenbon",
      at: scan.created_at,
      href: "/boodschappen",
      tone: scan.status === "failed" ? "urgent" : scan.status === "needs_review" ? "attention" : "success",
      timing: "recent",
    });
  }

  return items
    .filter((item) => Number.isFinite(new Date(item.at).getTime()))
    .sort((a, b) => {
      const aTime = new Date(a.at).getTime();
      const bTime = new Date(b.at).getTime();
      const aDistance = Math.abs(aTime - now);
      const bDistance = Math.abs(bTime - now);
      return a.timing === b.timing ? aDistance - bDistance : a.timing === "upcoming" ? -1 : 1;
    })
    .slice(0, limit);
}
