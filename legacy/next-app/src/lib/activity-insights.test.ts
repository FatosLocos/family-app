import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildActivityInsight } from "@/lib/activity-insights";
import type { AppData } from "@/lib/types";

describe("activity insights", () => {
  it("builds timeline quality from urgent, upcoming and recent activity", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "late-task",
          household_id: "demo-household",
          title: "Late taak",
          description: null,
          assignee_id: null,
          status: "open",
          priority: "hoog",
          due_date: "2026-07-10",
          recurrence: "none",
        },
        {
          id: "done-task",
          household_id: "demo-household",
          title: "Gedane taak",
          description: null,
          assignee_id: null,
          status: "done",
          priority: "normaal",
          due_date: "2026-07-11",
          recurrence: "none",
          completed_at: "2026-07-11T08:00:00.000Z",
        },
      ],
      calendarEvents: [
        {
          id: "event",
          household_id: "demo-household",
          title: "Afspraak",
          starts_at: "2026-07-12T10:00:00.000Z",
          ends_at: null,
          location: null,
          participant_ids: [],
        },
      ],
    };

    const insight = buildActivityInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.urgent.map((item) => item.id)).toContain("task-due-late-task");
    expect(insight.success.map((item) => item.id)).toContain("task-done-done-task");
    expect(insight.upcoming.map((item) => item.module)).toContain("Agenda");
    expect(insight.topSignal?.id).toBe("task-due-late-task");
    expect(insight.actions.find((action) => action.id === "urgent")?.done).toBe(false);
  });

  it("detects an empty activity timeline", () => {
    const data: AppData = {
      ...demoData,
      tasks: [],
      shoppingItems: [],
      householdNotes: [],
      calendarEvents: [],
      mealPlans: [],
      financeItems: [],
      maintenanceItems: [],
      householdDocuments: [],
      priceObservations: [],
      shoppingScans: [],
    };

    const insight = buildActivityInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.activity).toHaveLength(0);
    expect(insight.score).toBe(1);
    expect(insight.actions.find((action) => action.id === "baseline")?.done).toBe(false);
    expect(insight.actions.find((action) => action.id === "urgent")?.done).toBe(true);
  });
});
