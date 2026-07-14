import { buildActivityFeed, type ActivityItem } from "@/lib/activity";
import type { AppData } from "@/lib/types";

export type ActivityModuleCount = {
  module: string;
  count: number;
};

export type ActivityAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type ActivityInsight = {
  activity: ActivityItem[];
  upcoming: ActivityItem[];
  recent: ActivityItem[];
  urgent: ActivityItem[];
  attention: ActivityItem[];
  success: ActivityItem[];
  moduleCounts: ActivityModuleCount[];
  topSignal: ActivityItem | null;
  busiestModule: ActivityModuleCount | null;
  score: number;
  totalChecks: number;
  percent: number;
  actions: ActivityAction[];
};

export function buildActivityInsight(data: AppData, nowIso: string, limit = 60): ActivityInsight {
  const activity = buildActivityFeed(data, nowIso, limit);
  const upcoming = activity.filter((item) => item.timing === "upcoming");
  const recent = activity.filter((item) => item.timing === "recent");
  const urgent = activity.filter((item) => item.tone === "urgent");
  const attention = activity.filter((item) => item.tone === "attention");
  const success = activity.filter((item) => item.tone === "success");
  const moduleCounts = countByModule(activity);
  const topSignal = urgent[0] ?? attention[0] ?? upcoming[0] ?? recent[0] ?? null;
  const busiestModule = moduleCounts[0] ?? null;

  const actions: ActivityAction[] = [
    {
      id: "baseline",
      title: "Tijdlijn gevuld",
      detail: activity.length > 0 ? `${activity.length} signalen gevonden` : "Gebruik modules om activiteit op te bouwen.",
      href: "/snel",
      done: activity.length > 0,
    },
    {
      id: "upcoming",
      title: "Aankomende zaken zichtbaar",
      detail: upcoming.length > 0 ? `${upcoming.length} aankomende item${upcoming.length === 1 ? "" : "s"}` : "Geen aankomende items in de tijdlijn.",
      href: "/week",
      done: upcoming.length > 0,
    },
    {
      id: "recent",
      title: "Recent logboek actief",
      detail: recent.length > 0 ? `${recent.length} recente wijziging${recent.length === 1 ? "" : "en"}` : "Nog geen recente wijzigingen.",
      href: "/activiteit",
      done: recent.length > 0,
    },
    {
      id: "urgent",
      title: "Geen urgente activiteit",
      detail: urgent.length === 0 ? "Er staan geen urgente signalen in de tijdlijn" : `${urgent.length} urgent${urgent.length === 1 ? " signaal" : "e signalen"}`,
      href: topSignal?.href ?? "/meldingen",
      done: urgent.length === 0,
    },
    {
      id: "coverage",
      title: "Meerdere modules leveren signalen",
      detail: moduleCounts.length >= 3 ? `${moduleCounts.length} modules actief` : "Gebruik taken, agenda, boodschappen en onderhoud voor rijkere tijdlijn.",
      href: "/inrichting",
      done: moduleCounts.length >= 3,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    activity,
    upcoming,
    recent,
    urgent,
    attention,
    success,
    moduleCounts,
    topSignal,
    busiestModule,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
  };
}

function countByModule(items: ActivityItem[]) {
  const counts = new Map<string, number>();
  items.forEach((item) => counts.set(item.module, (counts.get(item.module) ?? 0) + 1));
  return Array.from(counts.entries())
    .map(([module, count]) => ({ module, count }))
    .sort((a, b) => b.count - a.count || a.module.localeCompare(b.module));
}
