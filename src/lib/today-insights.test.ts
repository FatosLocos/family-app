import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildTodayInsight } from "@/lib/today-insights";
import type { AppData } from "@/lib/types";

describe("buildTodayInsight", () => {
  it("prioritizes overdue tasks before other day signals", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "late-task",
          household_id: demoData.household.id,
          title: "Te laat",
          description: null,
          assignee_id: null,
          status: "open",
          priority: "hoog",
          due_date: "2026-07-10",
        },
      ],
      calendarEvents: [],
      mealPlans: [],
      shoppingItems: [],
      maintenanceItems: [],
      financeItems: [],
      householdNotes: [],
    };

    const insight = buildTodayInsight(data, "2026-07-11T08:00:00.000Z");

    expect(insight.overdueTasks).toHaveLength(1);
    expect(insight.focusAction.href).toBe("/taken?filter=open");
    expect(insight.dayPressure).toBeGreaterThanOrEqual(24);
    expect(insight.actions.find((action) => action.id === "late-tasks")?.done).toBe(false);
  });

  it("marks a quiet planned day as ready", () => {
    const data: AppData = {
      ...demoData,
      tasks: [],
      calendarEvents: [],
      shoppingItems: [],
      maintenanceItems: [],
      financeItems: [],
      householdNotes: [],
      mealPlans: [
        {
          id: "meal-1",
          household_id: demoData.household.id,
          planned_date: "2026-07-11",
          meal_type: "avondeten",
          title: "Pasta",
          notes: null,
          ingredients: null,
        },
      ],
    };

    const insight = buildTodayInsight(data, "2026-07-11T08:00:00.000Z");

    expect(insight.dayPressure).toBe(0);
    expect(insight.dayLabel).toBe("Rustig op schema");
    expect(insight.readinessScore).toBe(100);
    expect(insight.focusAction.href).toBe("/snel");
  });

  it("counts local Postgres Date objects as today", () => {
    const data: AppData = {
      ...demoData,
      tasks: [{ ...demoData.tasks[0], status: "open", due_date: new Date(2026, 6, 11) as unknown as string }],
      calendarEvents: [],
      shoppingItems: [],
      maintenanceItems: [],
      financeItems: [],
      householdNotes: [],
      mealPlans: [{ ...demoData.mealPlans[0], planned_date: new Date(2026, 6, 11) as unknown as string }],
    };

    const insight = buildTodayInsight(data, "2026-07-11T08:00:00.000Z");

    expect(insight.dueTodayTasks).toHaveLength(1);
    expect(insight.meals).toHaveLength(1);
  });
});
