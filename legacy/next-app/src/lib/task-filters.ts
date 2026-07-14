import { dateKey } from "@/lib/date-keys";
import type { Task } from "@/lib/types";

export type TaskFilter = "open" | "vandaag" | "alles";

export function normalizeTaskFilter(input: string | string[] | undefined): TaskFilter {
  const value = Array.isArray(input) ? input[0] : input;
  if (value === "vandaag" || value === "alles") return value;
  return "open";
}

export function filterTasks(tasks: Task[], filter: TaskFilter, now = new Date()) {
  if (filter === "alles") return tasks;

  if (filter === "open") {
    return tasks.filter((task) => task.status === "open");
  }

  const today = now.toISOString().slice(0, 10);
  return tasks.filter((task) => dateKey(task.due_date) === today);
}
