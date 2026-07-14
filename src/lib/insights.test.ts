import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildFamilyInsights } from "@/lib/insights";
import type { AppData } from "@/lib/types";

describe("family insights", () => {
  it("detects local Postgres Date objects in dashboard signals", () => {
    const data: AppData = {
      ...demoData,
      tasks: [{ ...demoData.tasks[0], status: "open", due_date: new Date(2026, 6, 11) as unknown as string }],
      maintenanceItems: [{ ...demoData.maintenanceItems[0], status: "open", due_date: new Date(2026, 6, 12) as unknown as string }],
      householdDocuments: [{ ...demoData.householdDocuments[0], expires_at: new Date(2026, 6, 20) as unknown as string }],
      mealPlans: [{ ...demoData.mealPlans[0], planned_date: new Date(2026, 6, 11) as unknown as string }],
      financeItems: [{ ...demoData.financeItems[0], status: "actief", due_date: new Date(2026, 6, 13) as unknown as string }],
      calendarEvents: [{ ...demoData.calendarEvents[0], starts_at: new Date(2026, 6, 11, 10, 0).toISOString() }],
      householdNotes: [],
      shoppingItems: [],
      shoppingProducts: [],
      financeBudgets: [],
      calendarIntegrations: demoData.calendarIntegrations,
      householdContacts: demoData.householdContacts,
      bankConnections: demoData.bankConnections,
      hasHomeAssistantConfig: true,
      hasHueConfig: true,
    };

    const insights = buildFamilyInsights(data, "2026-07-11T08:00:00.000Z");
    const ids = insights.map((insight) => insight.id);

    expect(ids).toContain("tasks-today");
    expect(ids).toContain("maintenance-soon");
    expect(ids).toContain("documents-expiring");
    expect(ids).toContain("meals-today");
    expect(ids).toContain("finance-due");
    expect(ids).toContain("events-today");
  });
});
