import { dateKey, dateSortValue } from "@/lib/date-keys";
import type { AppData, MaintenanceItem } from "@/lib/types";

const ESSENTIAL_AREAS = ["Veiligheid", "Techniek", "Tuin"];

export type MaintenanceAreaSummary = {
  area: string;
  count: number;
  open: number;
};

export type MaintenanceAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type MaintenanceReadiness = {
  open: MaintenanceItem[];
  overdue: MaintenanceItem[];
  thisWeek: MaintenanceItem[];
  thisMonth: MaintenanceItem[];
  recurring: MaintenanceItem[];
  withoutDate: MaintenanceItem[];
  withoutProvider: MaintenanceItem[];
  missingEssentialAreas: string[];
  nextItem: MaintenanceItem | null;
  areaSummaries: MaintenanceAreaSummary[];
  score: number;
  totalChecks: number;
  percent: number;
  actions: MaintenanceAction[];
};

export function buildMaintenanceReadiness(data: AppData, today = new Date().toISOString().slice(0, 10)): MaintenanceReadiness {
  const nextWeek = addDays(today, 7);
  const nextMonth = addDays(today, 30);
  const open = data.maintenanceItems.filter((item) => item.status === "open");
  const overdue = open.filter((item) => dateKey(item.due_date) !== null && dateKey(item.due_date)! < today);
  const thisWeek = open.filter((item) => isInRange(item.due_date, today, nextWeek));
  const thisMonth = open.filter((item) => isInRange(item.due_date, today, nextMonth));
  const recurring = data.maintenanceItems.filter((item) => item.frequency !== "none");
  const withoutDate = open.filter((item) => !item.due_date);
  const withoutProvider = open.filter((item) => !item.provider && isProviderUseful(item.area));
  const areaNames = new Set(data.maintenanceItems.map((item) => normalizeArea(item.area)));
  const missingEssentialAreas = ESSENTIAL_AREAS.filter((area) => !areaNames.has(area.toLowerCase()));
  const nextItem = [...open].filter((item) => item.due_date).sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date))[0] ?? null;
  const areaSummaries = buildAreaSummaries(data.maintenanceItems);

  const actions: MaintenanceAction[] = [
    {
      id: "baseline",
      title: "Onderhoudslijst gestart",
      detail: data.maintenanceItems.length > 0 ? `${data.maintenanceItems.length} huiszaken vastgelegd` : "Leg minimaal rookmelders, techniek en tuin/gebouw vast.",
      href: "/onderhoud",
      done: data.maintenanceItems.length > 0,
    },
    {
      id: "overdue",
      title: "Geen achterstand",
      detail: overdue.length === 0 ? "Er zijn geen verlopen onderhoudstaken" : `${overdue.length} onderhoudstaak${overdue.length === 1 ? "" : "en"} te laat`,
      href: "/onderhoud",
      done: overdue.length === 0,
    },
    {
      id: "dates",
      title: "Datum per open item",
      detail: withoutDate.length === 0 ? "Alle open items hebben een planning" : `${withoutDate.length} open item${withoutDate.length === 1 ? "" : "s"} zonder datum`,
      href: "/onderhoud",
      done: withoutDate.length === 0,
    },
    {
      id: "recurring",
      title: "Vaste controles ingericht",
      detail: recurring.length > 0 ? `${recurring.length} terugkerende controles` : "Maak vaste controles maandelijks, per kwartaal of jaarlijks.",
      href: "/routines",
      done: recurring.length > 0,
    },
    {
      id: "providers",
      title: "Contacten bij specialistisch werk",
      detail: withoutProvider.length === 0 ? "Specialistische items hebben leverancier/contact" : `${withoutProvider.length} item${withoutProvider.length === 1 ? "" : "s"} missen leverancier/contact`,
      href: "/onderhoud",
      done: withoutProvider.length === 0,
    },
    {
      id: "coverage",
      title: "Kernonderdelen gedekt",
      detail: missingEssentialAreas.length === 0 ? "Veiligheid, techniek en tuin/gebouw zijn gedekt" : `Mist: ${missingEssentialAreas.join(", ")}`,
      href: "/onderhoud",
      done: missingEssentialAreas.length === 0,
    },
  ];

  const score = actions.filter((action) => action.done).length;

  return {
    open,
    overdue,
    thisWeek,
    thisMonth,
    recurring,
    withoutDate,
    withoutProvider,
    missingEssentialAreas,
    nextItem,
    areaSummaries,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
  };
}

function buildAreaSummaries(items: MaintenanceItem[]) {
  return Object.entries(
    items.reduce<Record<string, MaintenanceAreaSummary>>((groups, item) => {
      const area = item.area || "Algemeen";
      groups[area] ??= { area, count: 0, open: 0 };
      groups[area].count += 1;
      if (item.status === "open") groups[area].open += 1;
      return groups;
    }, {}),
  )
    .map(([, summary]) => summary)
    .sort((a, b) => b.count - a.count || a.area.localeCompare(b.area))
    .slice(0, 5);
}

function normalizeArea(area: string | null) {
  const normalized = (area || "Algemeen").trim().toLowerCase();
  if (normalized.includes("rook") || normalized.includes("veilig")) return "veiligheid";
  if (normalized.includes("cv") || normalized.includes("ketel") || normalized.includes("techn")) return "techniek";
  if (normalized.includes("tuin") || normalized.includes("dak") || normalized.includes("gebouw")) return "tuin";
  return normalized;
}

function isProviderUseful(area: string | null) {
  const normalized = normalizeArea(area);
  return ["techniek", "tuin", "auto", "verzekering", "gebouw"].some((keyword) => normalized.includes(keyword));
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function isInRange(value: string | Date | null, start: string, end: string) {
  const key = dateKey(value);
  return key !== null && key >= start && key <= end;
}
