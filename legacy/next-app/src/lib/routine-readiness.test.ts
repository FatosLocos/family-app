import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildRoutineReadiness } from "@/lib/routine-readiness";
import type { AppData } from "@/lib/types";

describe("routine readiness", () => {
  it("detects missing owners, missing dates and due products", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "routine-task",
          household_id: "demo-household",
          title: "Container buiten",
          description: null,
          assignee_id: null,
          status: "open",
          priority: "normaal",
          due_date: null,
          recurrence: "weekly",
        },
      ],
      shoppingProducts: [
        {
          id: "milk",
          household_id: "demo-household",
          name: "Melk",
          category: "Zuivel",
          default_quantity: "2 pakken",
          recurrence: "weekly",
          purchase_count: 8,
          last_purchased_at: "2026-07-01",
        },
      ],
      maintenanceItems: [
        {
          id: "smoke",
          household_id: "demo-household",
          title: "Rookmelder testen",
          area: "Veiligheid",
          provider: null,
          due_date: null,
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
    };

    const readiness = buildRoutineReadiness(data, "2026-07-11");

    expect(readiness.total).toBe(3);
    expect(readiness.withoutOwner).toBe(1);
    expect(readiness.withoutDate).toBe(2);
    expect(readiness.dueProducts).toHaveLength(1);
    expect(readiness.nextSignal?.id).toBe("product-milk");
    expect(readiness.actions.find((action) => action.id === "owners")?.done).toBe(false);
    expect(readiness.actions.find((action) => action.id === "dates")?.done).toBe(false);
  });

  it("scores a complete routine setup", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "routine-task",
          household_id: "demo-household",
          title: "Container buiten",
          description: null,
          assignee_id: "demo-user-1",
          status: "open",
          priority: "normaal",
          due_date: "2026-07-12",
          recurrence: "weekly",
        },
      ],
      shoppingProducts: [
        {
          id: "milk",
          household_id: "demo-household",
          name: "Melk",
          category: "Zuivel",
          default_quantity: "2 pakken",
          recurrence: "weekly",
          purchase_count: 8,
          last_purchased_at: "2026-07-10",
        },
      ],
      maintenanceItems: [
        {
          id: "smoke",
          household_id: "demo-household",
          title: "Rookmelder testen",
          area: "Veiligheid",
          provider: null,
          due_date: "2026-07-15",
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
    };

    const readiness = buildRoutineReadiness(data, "2026-07-11");

    expect(readiness.score).toBe(readiness.totalChecks);
    expect(readiness.percent).toBe(100);
    expect(readiness.dueProducts).toHaveLength(0);
    expect(readiness.nextSignal?.id).toBe("task-routine-task");
  });

  it("keeps completed routine instances out of active work lists", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "done-routine",
          household_id: "demo-household",
          title: "Container buiten",
          description: null,
          assignee_id: "demo-user-1",
          status: "done",
          priority: "normaal",
          due_date: "2026-07-10",
          recurrence: "weekly",
        },
        {
          id: "next-routine",
          household_id: "demo-household",
          title: "Container buiten",
          description: null,
          assignee_id: "demo-user-1",
          status: "open",
          priority: "normaal",
          due_date: "2026-07-17",
          recurrence: "weekly",
        },
      ],
      maintenanceItems: [
        {
          id: "done-maintenance",
          household_id: "demo-household",
          title: "Filter vervangen",
          area: "Techniek",
          provider: null,
          due_date: "2026-07-10",
          frequency: "monthly",
          status: "done",
          notes: null,
          completed_at: "2026-07-10T12:00:00.000Z",
        },
      ],
    };

    const readiness = buildRoutineReadiness(data, "2026-07-11");

    expect(readiness.recurringTasks).toHaveLength(2);
    expect(readiness.activeRoutineTasks.map((task) => task.id)).toEqual(["next-routine"]);
    expect(readiness.activeRecurringMaintenance).toHaveLength(0);
    expect(readiness.dueRoutineTasks.map((task) => task.id)).toEqual(["next-routine"]);
  });

  it("handles Date due dates and purchase dates from database adapters", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "routine-task",
          household_id: "demo-household",
          title: "Container buiten",
          description: null,
          assignee_id: "demo-user-1",
          status: "open",
          priority: "normaal",
          due_date: new Date(2026, 6, 12) as unknown as string,
          recurrence: "weekly",
        },
      ],
      shoppingProducts: [
        {
          id: "milk",
          household_id: "demo-household",
          name: "Melk",
          category: "Zuivel",
          default_quantity: "2 pakken",
          recurrence: "weekly",
          purchase_count: 8,
          last_purchased_at: new Date(2026, 6, 1) as unknown as string,
        },
      ],
      maintenanceItems: [
        {
          id: "smoke",
          household_id: "demo-household",
          title: "Rookmelder testen",
          area: "Veiligheid",
          provider: null,
          due_date: new Date(2026, 6, 13) as unknown as string,
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
    };

    const readiness = buildRoutineReadiness(data, "2026-07-11");

    expect(readiness.dueRoutineTasks.map((task) => task.id)).toEqual(["routine-task"]);
    expect(readiness.dueProducts.map((product) => product.id)).toEqual(["milk"]);
    expect(readiness.dueMaintenance.map((item) => item.id)).toEqual(["smoke"]);
  });
});
