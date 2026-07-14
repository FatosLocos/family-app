import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildWeek, buildWeekInsight } from "@/lib/week-insights";
import type { AppData } from "@/lib/types";

describe("week insights", () => {
  it("builds a monday based week with module counts", () => {
    const insight = buildWeekInsight(demoData, "2026-07-11T09:00:00.000Z");

    expect(insight.weekStart).toBe("2026-07-06");
    expect(insight.weekEnd).toBe("2026-07-12");
    expect(insight.days).toHaveLength(7);
    expect(insight.weekMeals.length).toBeGreaterThan(0);
    expect(insight.openShopping).toBeGreaterThan(0);
    expect(insight.busiestDay?.load).toBeGreaterThan(0);
  });

  it("respects sunday week starts", () => {
    const days = buildWeek("2026-07-11", "sunday");

    expect(days[0]?.date).toBe("2026-07-05");
    expect(days[6]?.date).toBe("2026-07-11");
  });

  it("detects an empty week", () => {
    const data: AppData = {
      ...demoData,
      tasks: [],
      calendarEvents: [],
      mealPlans: [],
      financeItems: [],
      maintenanceItems: [],
      shoppingItems: [],
    };

    const insight = buildWeekInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.plannedItemCount).toBe(0);
    expect(insight.score).toBe(0);
    expect(insight.actions.every((action) => action.done === false)).toBe(true);
  });

  it("includes Date objects from local Postgres in the week", () => {
    const data: AppData = {
      ...demoData,
      tasks: [{ ...demoData.tasks[0], due_date: new Date(2026, 6, 11) as unknown as string }],
      calendarEvents: [],
      mealPlans: [{ ...demoData.mealPlans[0], planned_date: new Date(2026, 6, 11) as unknown as string }],
      financeItems: [{ ...demoData.financeItems[0], due_date: new Date(2026, 6, 11) as unknown as string }],
      maintenanceItems: [{ ...demoData.maintenanceItems[0], due_date: new Date(2026, 6, 11) as unknown as string }],
    };

    const insight = buildWeekInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.weekTasks).toHaveLength(1);
    expect(insight.weekMeals).toHaveLength(1);
    expect(insight.weekFinance).toHaveLength(1);
    expect(insight.weekMaintenance).toHaveLength(1);
  });
});
