import { dateKey, dateSortValue } from "@/lib/date-keys";
import type { AppData, CalendarEvent, FinanceItem, HouseholdNote, MaintenanceItem, MealPlan, ShoppingItem, Task } from "@/lib/types";

export type TodayFocus = {
  href: string;
  label: string;
  reason: string;
};

export type TodayAction = {
  id: string;
  label: string;
  detail: string;
  href: string;
  done: boolean;
  tone: "urgent" | "warning" | "good";
};

export type TodayInsight = {
  today: string;
  tomorrow: string;
  nextWeek: string;
  openTasks: Task[];
  overdueTasks: Task[];
  dueTodayTasks: Task[];
  todaysEvents: CalendarEvent[];
  tomorrowEvents: CalendarEvent[];
  meals: MealPlan[];
  openShopping: ShoppingItem[];
  shopping: ShoppingItem[];
  maintenanceAll: MaintenanceItem[];
  maintenance: MaintenanceItem[];
  financeDue: FinanceItem[];
  pinnedNotes: HouseholdNote[];
  dayPressure: number;
  dayLabel: string;
  focusAction: TodayFocus;
  actions: TodayAction[];
  readinessScore: number;
  completedActions: number;
};

export function buildTodayInsight(data: AppData, nowIso: string): TodayInsight {
  const today = dateKey(nowIso) ?? nowIso.slice(0, 10);
  const tomorrow = addDays(today, 1);
  const nextWeek = addDays(today, 7);
  const openTasks = data.tasks
    .filter((task) => !task.parent_task_id && task.status === "open" && dateKey(task.due_date) !== null && dateKey(task.due_date)! <= today)
    .sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date));
  const overdueTasks = openTasks.filter((task) => dateKey(task.due_date)! < today);
  const dueTodayTasks = openTasks.filter((task) => dateKey(task.due_date) === today);
  const todaysEvents = data.calendarEvents
    .filter((event) => dateKey(event.starts_at) === today)
    .sort((a, b) => dateSortValue(a.starts_at) - dateSortValue(b.starts_at));
  const tomorrowEvents = data.calendarEvents
    .filter((event) => dateKey(event.starts_at) === tomorrow)
    .sort((a, b) => dateSortValue(a.starts_at) - dateSortValue(b.starts_at))
    .slice(0, 4);
  const meals = data.mealPlans.filter((meal) => dateKey(meal.planned_date as string | Date) === today);
  const openShopping = data.shoppingItems.filter((item) => !item.checked);
  const maintenanceAll = data.maintenanceItems
    .filter((item) => item.status === "open" && dateKey(item.due_date) !== null && dateKey(item.due_date)! <= nextWeek)
    .sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date));
  const financeDue = data.financeItems
    .filter((item) => item.status !== "betaald" && dateKey(item.due_date) !== null && dateKey(item.due_date)! <= nextWeek)
    .sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date));
  const pinnedNotes = data.householdNotes.filter((note) => note.pinned).slice(0, 3);
  const dayPressure = Math.min(
    100,
    overdueTasks.length * 24 +
      dueTodayTasks.length * 14 +
      todaysEvents.length * 11 +
      Math.min(openShopping.length, 8) * 4 +
      maintenanceAll.length * 8 +
      financeDue.length * 8 +
      (meals.length === 0 ? 12 : 0),
  );
  const focusAction = getTodayFocus({
    overdueTasks: overdueTasks.length,
    dueTodayTasks: dueTodayTasks.length,
    todaysEvents: todaysEvents.length,
    mealsPlanned: meals.length,
    openShopping: openShopping.length,
    maintenanceDue: maintenanceAll.length,
    financeDue: financeDue.length,
    pinnedNotes: pinnedNotes.length,
  });
  const actions = buildTodayActions({
    overdueTasks: overdueTasks.length,
    dueTodayTasks: dueTodayTasks.length,
    todaysEvents: todaysEvents.length,
    mealsPlanned: meals.length,
    openShopping: openShopping.length,
    maintenanceDue: maintenanceAll.length,
    financeDue: financeDue.length,
  });
  const completedActions = actions.filter((action) => action.done).length;

  return {
    today,
    tomorrow,
    nextWeek,
    openTasks,
    overdueTasks,
    dueTodayTasks,
    todaysEvents,
    tomorrowEvents,
    meals,
    openShopping,
    shopping: openShopping.slice(0, 8),
    maintenanceAll,
    maintenance: maintenanceAll.slice(0, 5),
    financeDue,
    pinnedNotes,
    dayPressure,
    dayLabel: dayPressure >= 70 ? "Strakke dag" : dayPressure >= 35 ? "Normale dag" : "Rustig op schema",
    focusAction,
    actions,
    readinessScore: Math.round((completedActions / actions.length) * 100),
    completedActions,
  };
}

function buildTodayActions(metrics: {
  overdueTasks: number;
  dueTodayTasks: number;
  todaysEvents: number;
  mealsPlanned: number;
  openShopping: number;
  maintenanceDue: number;
  financeDue: number;
}): TodayAction[] {
  return [
    {
      id: "late-tasks",
      label: "Geen achterstallige taken",
      detail: metrics.overdueTasks === 0 ? "Alles is binnen deadline." : `${metrics.overdueTasks} taak${metrics.overdueTasks === 1 ? "" : "en"} te laat.`,
      href: "/taken?filter=open",
      done: metrics.overdueTasks === 0,
      tone: metrics.overdueTasks === 0 ? "good" : "urgent",
    },
    {
      id: "today-tasks",
      label: "Taken van vandaag helder",
      detail: metrics.dueTodayTasks === 0 ? "Geen taakdeadline vandaag." : `${metrics.dueTodayTasks} taak${metrics.dueTodayTasks === 1 ? "" : "en"} vandaag.`,
      href: "/taken?filter=vandaag",
      done: metrics.dueTodayTasks === 0,
      tone: metrics.dueTodayTasks === 0 ? "good" : "warning",
    },
    {
      id: "calendar",
      label: "Agenda bekeken",
      detail: metrics.todaysEvents === 0 ? "Geen afspraken vandaag." : `${metrics.todaysEvents} afspraak${metrics.todaysEvents === 1 ? "" : "en"} vandaag.`,
      href: "/agenda",
      done: metrics.todaysEvents === 0,
      tone: metrics.todaysEvents === 0 ? "good" : "warning",
    },
    {
      id: "meals",
      label: "Eten gepland",
      detail: metrics.mealsPlanned > 0 ? "Maaltijd staat klaar." : "Nog geen maaltijd voor vandaag.",
      href: "/boodschappen?tab=maaltijden",
      done: metrics.mealsPlanned > 0,
      tone: metrics.mealsPlanned > 0 ? "good" : "warning",
    },
    {
      id: "shopping",
      label: "Boodschappenlijst rustig",
      detail: metrics.openShopping === 0 ? "Geen open boodschappen." : `${metrics.openShopping} item${metrics.openShopping === 1 ? "" : "s"} open.`,
      href: "/boodschappen",
      done: metrics.openShopping === 0,
      tone: metrics.openShopping === 0 ? "good" : "warning",
    },
    {
      id: "house-money",
      label: "Huis en geld gecheckt",
      detail:
        metrics.maintenanceDue + metrics.financeDue === 0
          ? "Geen huis- of betaalmomenten deze week."
          : `${metrics.maintenanceDue} huiszaken, ${metrics.financeDue} betaalmomenten.`,
      href: metrics.maintenanceDue > 0 ? "/onderhoud" : "/geld",
      done: metrics.maintenanceDue + metrics.financeDue === 0,
      tone: metrics.maintenanceDue + metrics.financeDue === 0 ? "good" : "warning",
    },
  ];
}

function getTodayFocus(metrics: {
  overdueTasks: number;
  dueTodayTasks: number;
  todaysEvents: number;
  mealsPlanned: number;
  openShopping: number;
  maintenanceDue: number;
  financeDue: number;
  pinnedNotes: number;
}): TodayFocus {
  if (metrics.overdueTasks > 0) {
    return { href: "/taken?filter=open", label: "Open taken", reason: "Begin met taken waarvan de deadline al voorbij is." };
  }
  if (metrics.dueTodayTasks > 0) {
    return { href: "/taken?filter=vandaag", label: "Taken vandaag", reason: "Er staan taken op de planning die vandaag af moeten." };
  }
  if (metrics.todaysEvents > 0) {
    return { href: "/agenda", label: "Bekijk agenda", reason: "De agenda bepaalt vandaag waarschijnlijk de volgorde." };
  }
  if (metrics.mealsPlanned === 0) {
    return { href: "/boodschappen?tab=maaltijden", label: "Plan eten", reason: "Er staat nog geen maaltijd voor vandaag klaar." };
  }
  if (metrics.openShopping > 0) {
    return { href: "/boodschappen", label: "Open lijst", reason: "De boodschappenlijst heeft nog open items." };
  }
  if (metrics.maintenanceDue > 0) {
    return { href: "/onderhoud", label: "Huiszaken", reason: "Er zijn huiszaken die deze week aandacht vragen." };
  }
  if (metrics.financeDue > 0) {
    return { href: "/geld", label: "Betaalmomenten", reason: "Er komen betaalmomenten aan die je kunt controleren." };
  }
  if (metrics.pinnedNotes > 0) {
    return { href: "/prikbord", label: "Prikbord", reason: "Er staan vastgezette gezinsberichten klaar." };
  }
  return { href: "/snel", label: "Snel toevoegen", reason: "Er is geen urgente actie gevonden. Voeg iets toe zodra het opkomt." };
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
