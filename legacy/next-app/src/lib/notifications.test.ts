import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildNotifications } from "@/lib/notifications";
import type { AppData } from "@/lib/types";

describe("notifications", () => {
  it("labels local Postgres Date objects correctly", () => {
    const data: AppData = {
      ...demoData,
      tasks: [{ ...demoData.tasks[0], status: "open", due_date: new Date(2026, 6, 11) as unknown as string }],
      calendarEvents: [{ ...demoData.calendarEvents[0], starts_at: new Date(2026, 6, 12, 11, 0).toISOString() }],
      maintenanceItems: [{ ...demoData.maintenanceItems[0], status: "open", due_date: new Date(2026, 6, 10) as unknown as string }],
      financeItems: [{ ...demoData.financeItems[0], status: "actief", due_date: new Date(2026, 6, 13) as unknown as string }],
      householdDocuments: [{ ...demoData.householdDocuments[0], expires_at: new Date(2026, 6, 20) as unknown as string }],
      shoppingProducts: [],
      householdNotes: [],
      calendarIntegrations: [],
    };

    const notifications = buildNotifications(data, "2026-07-11T08:00:00.000Z");

    expect(notifications.find((item) => item.id.startsWith("task-"))?.dueLabel).toBe("Vandaag");
    expect(notifications.find((item) => item.id.startsWith("event-"))?.dueLabel).toBe("Morgen");
    expect(notifications.find((item) => item.id.startsWith("maintenance-"))?.tone).toBe("urgent");
    expect(notifications.find((item) => item.id.startsWith("finance-"))?.dueLabel).toContain("jul");
    expect(notifications.find((item) => item.id.startsWith("document-"))?.dueLabel.toLowerCase()).toContain("vervalt");
  });
});
