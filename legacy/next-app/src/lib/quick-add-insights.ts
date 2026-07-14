import { dateKey } from "@/lib/date-keys";
import type { AppData } from "@/lib/types";

export type QuickAddAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
  kind: "task" | "shopping" | "note" | "event" | "meal" | "finance";
};

export type QuickAddInsight = {
  openTasks: number;
  dueToday: number;
  openShopping: number;
  pinnedNotes: number;
  upcomingEvents: number;
  upcomingMeals: number;
  upcomingPlanning: number;
  activeFinanceItems: number;
  missingSignals: string[];
  suggestedKind: QuickAddAction["kind"];
  suggestedTitle: string;
  suggestedDetail: string;
  score: number;
  totalChecks: number;
  percent: number;
  actions: QuickAddAction[];
};

export function buildQuickAddInsight(data: AppData, today = new Date().toISOString().slice(0, 10)): QuickAddInsight {
  const openTasks = data.tasks.filter((task) => task.status === "open").length;
  const dueToday = data.tasks.filter((task) => task.status === "open" && dateKey(task.due_date) === today).length;
  const openShopping = data.shoppingItems.filter((item) => !item.checked).length;
  const pinnedNotes = data.householdNotes.filter((note) => note.pinned).length;
  const upcomingEvents = data.calendarEvents.filter((event) => dateKey(event.starts_at)! >= today).length;
  const upcomingMeals = data.mealPlans.filter((meal) => dateKey(meal.planned_date as string | Date)! >= today).length;
  const activeFinanceItems = data.financeItems.filter((item) => item.status !== "betaald").length;

  const actions: QuickAddAction[] = [
    {
      id: "task",
      title: "Taakbuffer",
      detail: openTasks > 0 ? `${openTasks} open taak${openTasks === 1 ? "" : "en"}` : "Leg de eerste open taak vast.",
      href: "/snel?kind=task",
      done: openTasks > 0,
      kind: "task",
    },
    {
      id: "shopping",
      title: "Boodschappenbuffer",
      detail: openShopping > 0 ? `${openShopping} open boodschap${openShopping === 1 ? "" : "pen"}` : "Zet een ontbrekend product op de lijst.",
      href: "/snel?kind=shopping",
      done: openShopping > 0,
      kind: "shopping",
    },
    {
      id: "meal",
      title: "Eetplanning",
      detail: upcomingMeals > 0 ? `${upcomingMeals} maaltijd${upcomingMeals === 1 ? "" : "en"} gepland` : "Plan een maaltijd zodat boodschappen aansluiten.",
      href: "/snel?kind=meal",
      done: upcomingMeals > 0,
      kind: "meal",
    },
    {
      id: "note",
      title: "Prikbordanker",
      detail: pinnedNotes > 0 ? `${pinnedNotes} vastgezet bericht${pinnedNotes === 1 ? "" : "en"}` : "Zet een belangrijk gezinsbericht vast.",
      href: "/snel?kind=note",
      done: pinnedNotes > 0,
      kind: "note",
    },
    {
      id: "event",
      title: "Planning",
      detail: upcomingEvents > 0 ? `${upcomingEvents} afspraak${upcomingEvents === 1 ? "" : "en"} gepland` : "Leg een afspraak of herinnering vast.",
      href: "/snel?kind=event",
      done: upcomingEvents > 0,
      kind: "event",
    },
    {
      id: "finance",
      title: "Betaalmomenten",
      detail: activeFinanceItems > 0 ? `${activeFinanceItems} gelditem${activeFinanceItems === 1 ? "" : "s"} actief` : "Leg een betaalmoment of abonnement vast.",
      href: "/snel?kind=finance",
      done: activeFinanceItems > 0,
      kind: "finance",
    },
  ];
  const score = actions.filter((action) => action.done).length;
  const nextAction = actions.find((action) => !action.done) ?? actions[0];

  return {
    openTasks,
    dueToday,
    openShopping,
    pinnedNotes,
    upcomingEvents,
    upcomingMeals,
    upcomingPlanning: upcomingEvents + upcomingMeals,
    activeFinanceItems,
    missingSignals: actions.filter((action) => !action.done).map((action) => labelForKind(action.kind)),
    suggestedKind: nextAction.kind,
    suggestedTitle: nextAction.done ? "Alles heeft al basisvulling" : `Suggestie: ${labelForKind(nextAction.kind)}`,
    suggestedDetail: nextAction.done
      ? "Gebruik snelle invoer voor ad-hoc dingen die anders blijven hangen."
      : "Gebruik het formulier hieronder en kies het type dat past bij de suggestie.",
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
  };
}

function labelForKind(kind: QuickAddAction["kind"]) {
  if (kind === "task") return "Nieuwe taak";
  if (kind === "shopping") return "Boodschap";
  if (kind === "meal") return "Maaltijd";
  if (kind === "note") return "Prikbordbericht";
  if (kind === "event") return "Afspraak";
  return "Betaalmoment";
}
