import { dateKey } from "@/lib/date-keys";
import type { AppData } from "@/lib/types";

export type WeekDay = {
  date: string;
  label: string;
  dayName: string;
  load: number;
};

export type WeekAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type WeekInsight = {
  today: string;
  days: WeekDay[];
  weekStart: string;
  weekEnd: string;
  weekTasks: AppData["tasks"];
  weekEvents: AppData["calendarEvents"];
  weekMeals: AppData["mealPlans"];
  weekFinance: AppData["financeItems"];
  weekMaintenance: AppData["maintenanceItems"];
  openShopping: number;
  busiestDay: WeekDay | null;
  financeTotal: number;
  plannedItemCount: number;
  score: number;
  totalChecks: number;
  percent: number;
  actions: WeekAction[];
};

export function buildWeekInsight(data: AppData, nowIso: string): WeekInsight {
  const today = nowIso.slice(0, 10);
  const baseDays = buildWeek(today, data.householdPreferences.week_starts_on);
  const weekStart = baseDays[0]?.date ?? today;
  const weekEnd = baseDays[baseDays.length - 1]?.date ?? today;
  const weekTasks = data.tasks.filter((task) => !task.parent_task_id && task.status === "open" && isInRange(task.due_date, weekStart, weekEnd));
  const weekEvents = data.calendarEvents.filter((event) => isInRange(event.starts_at, weekStart, weekEnd));
  const weekMeals = data.mealPlans.filter((meal) => isInRange(meal.planned_date as string | Date, weekStart, weekEnd));
  const weekFinance = data.financeItems.filter((item) => item.status !== "betaald" && isInRange(item.due_date, weekStart, weekEnd));
  const weekMaintenance = data.maintenanceItems.filter((item) => item.status === "open" && isInRange(item.due_date, weekStart, weekEnd));
  const openShopping = data.shoppingItems.filter((item) => !item.checked).length;
  const days = baseDays.map((day) => ({
    ...day,
    load: dayLoad(day.date, weekEvents, weekTasks, weekMeals, weekFinance, weekMaintenance),
  }));
  const busiestDay = [...days].sort((a, b) => b.load - a.load)[0] ?? null;
  const financeTotal = weekFinance.reduce((total, item) => total + item.amount_cents, 0);
  const plannedItemCount = weekEvents.length + weekTasks.length + weekMeals.length;

  const actions: WeekAction[] = [
    {
      id: "planning",
      title: "Weekplanning gevuld",
      detail: plannedItemCount > 0 ? `${plannedItemCount} geplande items` : "Plan afspraken, taken of maaltijden voor deze week.",
      href: "/snel",
      done: plannedItemCount > 0,
    },
    {
      id: "tasks",
      title: "Taken hebben deadline",
      detail: weekTasks.length > 0 ? `${weekTasks.length} taak${weekTasks.length === 1 ? "" : "en"} deze week` : "Geen open taken met deadline deze week.",
      href: "/taken",
      done: weekTasks.length > 0,
    },
    {
      id: "meals",
      title: "Maaltijden gepland",
      detail: weekMeals.length >= 4 ? `${weekMeals.length} eetmomenten gepland` : `${Math.max(0, 4 - weekMeals.length)} maaltijd${4 - weekMeals.length === 1 ? "" : "en"} extra geeft rust`,
      href: "/boodschappen?tab=maaltijden",
      done: weekMeals.length >= 4,
    },
    {
      id: "shopping",
      title: "Boodschappen zichtbaar",
      detail: openShopping > 0 ? `${openShopping} open boodschap${openShopping === 1 ? "" : "pen"}` : "Geen open boodschappen voor de week.",
      href: "/boodschappen",
      done: openShopping > 0,
    },
    {
      id: "home",
      title: "Huiszaken ingepland",
      detail: weekMaintenance.length > 0 ? `${weekMaintenance.length} huiszaak${weekMaintenance.length === 1 ? "" : "en"} deze week` : "Geen onderhoud met deadline deze week.",
      href: "/onderhoud",
      done: weekMaintenance.length > 0,
    },
    {
      id: "finance",
      title: "Geldmomenten zichtbaar",
      detail: weekFinance.length > 0 ? `${weekFinance.length} betaalmoment${weekFinance.length === 1 ? "" : "en"} deze week` : "Geen betaalmomenten deze week.",
      href: "/geld",
      done: weekFinance.length > 0,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    today,
    days,
    weekStart,
    weekEnd,
    weekTasks,
    weekEvents,
    weekMeals,
    weekFinance,
    weekMaintenance,
    openShopping,
    busiestDay,
    financeTotal,
    plannedItemCount,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
  };
}

export function buildWeek(today: string, weekStartsOn: "monday" | "sunday"): Omit<WeekDay, "load">[] {
  const start = new Date(`${today}T12:00:00.000Z`);
  const day = start.getUTCDay();
  const offset = weekStartsOn === "monday" ? (day + 6) % 7 : day;
  start.setUTCDate(start.getUTCDate() - offset);
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(start);
    date.setUTCDate(date.getUTCDate() + index);
    const iso = date.toISOString().slice(0, 10);
    return {
      date: iso,
      label: new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "short" }).format(date),
      dayName: new Intl.DateTimeFormat("nl-NL", { weekday: "short" }).format(date),
    };
  });
}

function dayLoad(
  date: string,
  events: AppData["calendarEvents"],
  tasks: AppData["tasks"],
  meals: AppData["mealPlans"],
  finance: AppData["financeItems"],
  maintenance: AppData["maintenanceItems"],
) {
  return (
    events.filter((event) => dateKey(event.starts_at) === date).length +
    tasks.filter((task) => dateKey(task.due_date) === date).length +
    meals.filter((meal) => dateKey(meal.planned_date as string | Date) === date).length +
    finance.filter((item) => dateKey(item.due_date) === date).length +
    maintenance.filter((item) => dateKey(item.due_date) === date).length
  );
}

function isInRange(value: string | Date | null, start: string, end: string) {
  const key = dateKey(value);
  return key !== null && key >= start && key <= end;
}
