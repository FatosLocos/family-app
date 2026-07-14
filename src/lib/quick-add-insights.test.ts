import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildQuickAddInsight } from "@/lib/quick-add-insights";
import type { AppData } from "@/lib/types";

describe("quick add insights", () => {
  it("suggests the first missing quick-add domain", () => {
    const data: AppData = {
      ...demoData,
      tasks: [],
      shoppingItems: [],
      mealPlans: [],
      householdNotes: [],
      calendarEvents: [],
      financeItems: [],
    };

    const insight = buildQuickAddInsight(data, "2026-07-11");

    expect(insight.score).toBe(0);
    expect(insight.suggestedKind).toBe("task");
    expect(insight.missingSignals).toEqual(["Nieuwe taak", "Boodschap", "Maaltijd", "Prikbordbericht", "Afspraak", "Betaalmoment"]);
    expect(insight.actions.find((action) => action.id === "finance")?.done).toBe(false);
  });

  it("scores a filled quick-add command center", () => {
    const insight = buildQuickAddInsight(demoData, "2026-07-11");

    expect(insight.openTasks).toBeGreaterThan(0);
    expect(insight.openShopping).toBeGreaterThan(0);
    expect(insight.pinnedNotes).toBeGreaterThan(0);
    expect(insight.upcomingPlanning).toBeGreaterThan(0);
    expect(insight.score).toBe(insight.totalChecks);
    expect(insight.percent).toBe(100);
    expect(insight.suggestedTitle).toBe("Alles heeft al basisvulling");
  });
});
