import { describe, expect, it } from "vitest";
import { filterTasks, normalizeTaskFilter } from "@/lib/task-filters";
import type { Task } from "@/lib/types";

const tasks: Task[] = [
  {
    id: "1",
    household_id: "h",
    title: "Vandaag open",
    description: null,
    assignee_id: null,
    status: "open",
    priority: "normaal",
    due_date: "2026-07-08",
  },
  {
    id: "2",
    household_id: "h",
    title: "Later open",
    description: null,
    assignee_id: null,
    status: "open",
    priority: "laag",
    due_date: "2026-07-09",
  },
  {
    id: "3",
    household_id: "h",
    title: "Vandaag klaar",
    description: null,
    assignee_id: null,
    status: "done",
    priority: "hoog",
    due_date: "2026-07-08",
  },
];

describe("task filters", () => {
  it("normalizes unknown filters to open", () => {
    expect(normalizeTaskFilter(undefined)).toBe("open");
    expect(normalizeTaskFilter("anders")).toBe("open");
    expect(normalizeTaskFilter("vandaag")).toBe("vandaag");
    expect(normalizeTaskFilter("alles")).toBe("alles");
  });

  it("filters open, today and all tasks", () => {
    const now = new Date("2026-07-08T12:00:00.000Z");
    expect(filterTasks(tasks, "open", now).map((task) => task.id)).toEqual(["1", "2"]);
    expect(filterTasks(tasks, "vandaag", now).map((task) => task.id)).toEqual(["1", "3"]);
    expect(filterTasks(tasks, "alles", now).map((task) => task.id)).toEqual(["1", "2", "3"]);
  });

  it("filters Date objects from local Postgres as today", () => {
    const now = new Date("2026-07-08T12:00:00.000Z");
    const postgresTasks: Task[] = [{ ...tasks[0], due_date: new Date(2026, 6, 8) as unknown as string }];

    expect(filterTasks(postgresTasks, "vandaag", now).map((task) => task.id)).toEqual(["1"]);
  });
});
