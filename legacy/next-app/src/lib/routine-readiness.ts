import { dateKey } from "@/lib/date-keys";
import { memberName, shortDate } from "@/lib/format";
import type { AppData, MaintenanceItem, ShoppingProduct, Task } from "@/lib/types";

export type RoutineAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type RoutineSignal = {
  id: string;
  title: string;
  detail: string;
  href: string;
  type: "task" | "product" | "maintenance";
};

export type RoutineReadiness = {
  recurringTasks: Task[];
  recurringProducts: ShoppingProduct[];
  recurringMaintenance: MaintenanceItem[];
  activeRoutineTasks: Task[];
  activeRecurringMaintenance: MaintenanceItem[];
  dueRoutineTasks: Task[];
  dueProducts: ShoppingProduct[];
  dueMaintenance: MaintenanceItem[];
  total: number;
  dueThisWeek: number;
  withoutOwner: number;
  withoutDate: number;
  score: number;
  totalChecks: number;
  percent: number;
  actions: RoutineAction[];
  nextSignal: RoutineSignal | null;
};

export function buildRoutineReadiness(data: AppData, today = new Date().toISOString().slice(0, 10)): RoutineReadiness {
  const todayKey = dateKey(today) ?? today;
  const recurringTasks = data.tasks
    .filter((task) => !task.parent_task_id && task.recurrence && task.recurrence !== "none")
    .sort((a, b) => recurrenceScore(a.recurrence) - recurrenceScore(b.recurrence));
  const recurringProducts = data.shoppingProducts
    .filter((product) => product.recurrence !== "none")
    .sort((a, b) => recurrenceScore(a.recurrence) - recurrenceScore(b.recurrence));
  const recurringMaintenance = data.maintenanceItems
    .filter((item) => item.frequency !== "none")
    .sort((a, b) => maintenanceScore(a.frequency) - maintenanceScore(b.frequency));
  const activeRoutineTasks = recurringTasks.filter((task) => task.status === "open");
  const activeRecurringMaintenance = recurringMaintenance.filter((item) => item.status === "open");
  const total = recurringTasks.length + recurringProducts.length + recurringMaintenance.length;
  const nextWeek = addDays(todayKey, 7);
  const dueRoutineTasks = activeRoutineTasks.filter((task) => {
    const dueDate = dateKey(task.due_date);
    return dueDate && dueDate <= nextWeek;
  });
  const dueMaintenance = activeRecurringMaintenance.filter((item) => {
    const dueDate = dateKey(item.due_date);
    return dueDate && dueDate <= nextWeek;
  });
  const dueProducts = recurringProducts.filter((product) => isProductDue(product.last_purchased_at, product.recurrence, todayKey));
  const withoutOwner = recurringTasks.filter((task) => !task.assignee_id).length;
  const withoutDate = recurringTasks.filter((task) => !task.due_date).length + recurringMaintenance.filter((item) => !item.due_date).length;

  const actions: RoutineAction[] = [
    {
      id: "baseline",
      title: "Minimaal een vast ritme",
      detail: total > 0 ? `${total} routines actief` : "Maak je eerste vaste taak, product of onderhoudscontrole.",
      href: "/routines",
      done: total > 0,
    },
    {
      id: "tasks",
      title: "Terugkerende taken",
      detail: recurringTasks.length > 0 ? `${recurringTasks.length} taken met herhaling` : "Maak vaste gezinstaken aan met een herhaling.",
      href: "/taken",
      done: recurringTasks.length > 0,
    },
    {
      id: "shopping",
      title: "Terugkerende boodschappen",
      detail: recurringProducts.length > 0 ? `${recurringProducts.length} producten met ritme` : "Zet veelgekochte producten op wekelijks, tweewekelijks of maandelijks.",
      href: "/boodschappen",
      done: recurringProducts.length > 0,
    },
    {
      id: "maintenance",
      title: "Periodiek onderhoud",
      detail: recurringMaintenance.length > 0 ? `${recurringMaintenance.length} vaste huiscontroles` : "Plan controles zoals rookmelders, filters en CV.",
      href: "/onderhoud",
      done: recurringMaintenance.length > 0,
    },
    {
      id: "owners",
      title: "Eigenaar per taak",
      detail: withoutOwner === 0 ? "Alle taakroutines hebben een gezinslid" : `${withoutOwner} taakroutine${withoutOwner === 1 ? "" : "s"} zonder eigenaar`,
      href: "/taken",
      done: withoutOwner === 0,
    },
    {
      id: "dates",
      title: "Planning per routine",
      detail: withoutDate === 0 ? "Alle taak- en onderhoudsroutines hebben een datum" : `${withoutDate} routine${withoutDate === 1 ? "" : "s"} zonder datum`,
      href: "/week",
      done: withoutDate === 0,
    },
  ];

  const score = actions.filter((action) => action.done).length;
  const nextSignal = buildNextSignal({ dueRoutineTasks, dueProducts, dueMaintenance, data });

  return {
    recurringTasks,
    recurringProducts,
    recurringMaintenance,
    activeRoutineTasks,
    activeRecurringMaintenance,
    dueRoutineTasks,
    dueProducts,
    dueMaintenance,
    total,
    dueThisWeek: dueRoutineTasks.length + dueProducts.length + dueMaintenance.length,
    withoutOwner,
    withoutDate,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
    nextSignal,
  };
}

export function recurrenceLabel(value?: string | null) {
  if (value === "daily") return "Dagelijks";
  if (value === "weekly") return "Wekelijks";
  if (value === "biweekly") return "Elke twee weken";
  if (value === "monthly") return "Maandelijks";
  return "Terugkerend";
}

export function maintenanceLabel(value: string) {
  if (value === "monthly") return "Maandelijks";
  if (value === "quarterly") return "Elk kwartaal";
  if (value === "yearly") return "Jaarlijks";
  return "Terugkerend";
}

function buildNextSignal({
  dueRoutineTasks,
  dueProducts,
  dueMaintenance,
  data,
}: {
  dueRoutineTasks: Task[];
  dueProducts: ShoppingProduct[];
  dueMaintenance: MaintenanceItem[];
  data: AppData;
}): RoutineSignal | null {
  return [
    ...dueRoutineTasks.map((task) => ({
      id: `task-${task.id}`,
      title: task.title,
      detail: `${recurrenceLabel(task.recurrence)} · ${memberName(task.assignee_id, data.members)} · ${shortDate(task.due_date)}`,
      href: "/taken?filter=vandaag",
      type: "task" as const,
    })),
    ...dueProducts.map((product) => ({
      id: `product-${product.id}`,
      title: product.name,
      detail: `${recurrenceLabel(product.recurrence)} · ${product.default_quantity ?? "Geen hoeveelheid"}`,
      href: "/boodschappen",
      type: "product" as const,
    })),
    ...dueMaintenance.map((item) => ({
      id: `maintenance-${item.id}`,
      title: item.title,
      detail: `${maintenanceLabel(item.frequency)} · ${shortDate(item.due_date)}`,
      href: "/onderhoud",
      type: "maintenance" as const,
    })),
  ][0] ?? null;
}

function recurrenceScore(value?: string | null) {
  if (value === "daily") return 0;
  if (value === "weekly") return 1;
  if (value === "biweekly") return 2;
  if (value === "monthly") return 3;
  return 4;
}

function maintenanceScore(value: string) {
  if (value === "monthly") return 1;
  if (value === "quarterly") return 2;
  if (value === "yearly") return 3;
  return 4;
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function isProductDue(lastPurchasedAt: string | null, recurrence: string, today: string) {
  const days = recurrence === "weekly" ? 7 : recurrence === "biweekly" ? 14 : recurrence === "monthly" ? 30 : null;
  if (!days) return false;
  if (!lastPurchasedAt) return true;
  const lastKey = dateKey(lastPurchasedAt);
  if (!lastKey) return true;
  const diff = Math.floor((new Date(`${today}T12:00:00.000Z`).getTime() - new Date(`${lastKey}T12:00:00.000Z`).getTime()) / 86_400_000);
  return diff >= days;
}
