import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildNotificationInsight } from "@/lib/notification-insights";
import type { AppData } from "@/lib/types";

describe("notification insights", () => {
  it("prioritizes urgent notifications and builds module counts", () => {
    const data: AppData = {
      ...demoData,
      calendarIntegrations: [
        {
          id: "calendar",
          household_id: "demo-household",
          user_id: "demo-user-1",
          provider: "outlook",
          status: "configured",
          display_name: "Outlook",
          account_email: "fatih@example.com",
          tenant_id: "tenant",
          last_sync_at: "2026-07-10T10:00:00.000Z",
        },
      ],
      calendarEvents: [],
      financeItems: [],
      householdDocuments: [],
      tasks: [
        {
          id: "task-late",
          household_id: "demo-household",
          title: "Verlopen taak",
          description: "Moest gisteren",
          assignee_id: "demo-user-1",
          status: "open",
          priority: "hoog",
          due_date: "2026-07-10",
          recurrence: "none",
        },
      ],
      maintenanceItems: [
        {
          id: "maintenance-today",
          household_id: "demo-household",
          title: "Rookmelder testen",
          area: "Veiligheid",
          provider: null,
          due_date: "2026-07-11",
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
      householdNotes: [],
      shoppingProducts: [],
    };

    const insight = buildNotificationInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.urgent).toHaveLength(1);
    expect(insight.attention).toHaveLength(1);
    expect(insight.topAction?.id).toBe("task-task-late");
    expect(insight.briefingTone).toBe("urgent");
    expect(insight.pressureScore).toBe(42);
    expect(insight.moduleCounts.map((item) => item.module)).toEqual(["Onderhoud", "Taken"]);
  });

  it("marks setup-only notifications as quiet", () => {
    const data: AppData = {
      ...demoData,
      calendarIntegrations: [],
      tasks: [],
      calendarEvents: [],
      maintenanceItems: [],
      financeItems: [],
      householdDocuments: [],
      shoppingProducts: [],
      householdNotes: [],
    };

    const insight = buildNotificationInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.notifications.map((item) => item.id)).toEqual(["setup-calendar"]);
    expect(insight.info).toHaveLength(1);
    expect(insight.quiet).toBe(true);
    expect(insight.briefingTone).toBe("info");
  });

  it("builds a personal digest preview from member notification preferences", () => {
    const data: AppData = {
      ...demoData,
      members: [
        {
          ...demoData.members[0],
          user_id: "demo-user-1",
          profile: {
            ...demoData.members[0].profile,
            id: "demo-user-1",
            full_name: "Fatih",
            email: "fatih@example.com",
            notification_email: true,
            digest_time: "07:30",
          },
        },
        {
          ...demoData.members[0],
          user_id: "demo-user-2",
          profile: {
            id: "demo-user-2",
            full_name: "Geen mail",
            email: "geenmail@example.com",
            notification_email: false,
            digest_time: "08:00",
          },
        },
      ],
      calendarIntegrations: [],
      calendarEvents: [],
      financeItems: [],
      householdDocuments: [],
      maintenanceItems: [],
      householdNotes: [],
      shoppingProducts: [],
      tasks: [
        {
          id: "task-late",
          household_id: "demo-household",
          title: "Verlopen taak",
          description: null,
          assignee_id: "demo-user-1",
          status: "open",
          priority: "hoog",
          due_date: "2026-07-10",
          recurrence: "none",
        },
      ],
    };

    const insight = buildNotificationInsight(data, "2026-07-11T04:45:00.000Z");

    expect(insight.digest.ready).toBe(true);
    expect(insight.digest.enabledRecipients).toHaveLength(1);
    expect(insight.digest.nextTime).toBe("07:30 vandaag");
    expect(insight.digest.subject).toContain("urgente");
    expect(insight.digest.previewItems.map((item) => item.id)).toContain("task-task-late");
  });
});
