import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildPeopleWorkloadInsight } from "@/lib/people-workload";
import type { AppData } from "@/lib/types";

describe("people workload insight", () => {
  it("detects unassigned tasks and member loads", () => {
    const insight = buildPeopleWorkloadInsight(demoData, "2026-07-11T09:00:00.000Z");

    expect(insight.openTasks.length).toBeGreaterThan(0);
    expect(insight.unassignedTasks.map((task) => task.id)).toContain("task-2");
    expect(insight.memberLoads).toHaveLength(demoData.members.length);
    expect(insight.busiestMember?.load).toBeGreaterThanOrEqual(0);
    expect(insight.actions.find((action) => action.id === "owners")?.done).toBe(false);
  });

  it("scores a distributed household", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "task-1",
          household_id: "demo-household",
          title: "Taak Fatih",
          description: null,
          assignee_id: "demo-user-1",
          status: "open",
          priority: "normaal",
          due_date: "2026-07-11",
        },
        {
          id: "task-2",
          household_id: "demo-household",
          title: "Taak gezinslid",
          description: null,
          assignee_id: "demo-user-2",
          status: "open",
          priority: "normaal",
          due_date: "2026-07-12",
        },
      ],
      calendarEvents: [
        {
          id: "event-1",
          household_id: "demo-household",
          title: "Gezinsafspraak",
          starts_at: "2026-07-12T10:00:00.000Z",
          ends_at: null,
          location: null,
          participant_ids: ["demo-user-1", "demo-user-2"],
        },
      ],
    };

    const insight = buildPeopleWorkloadInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.unassignedTasks).toHaveLength(0);
    expect(insight.quietMembers).toHaveLength(0);
    expect(insight.score).toBe(insight.totalChecks);
    expect(insight.percent).toBe(100);
  });

  it("handles Date values for tasks and events from database adapters", () => {
    const data: AppData = {
      ...demoData,
      tasks: [
        {
          id: "task-1",
          household_id: "demo-household",
          title: "Taak Fatih",
          description: null,
          assignee_id: "demo-user-1",
          status: "open",
          priority: "normaal",
          due_date: new Date(2026, 6, 12) as unknown as string,
        },
      ],
      calendarEvents: [
        {
          id: "event-1",
          household_id: "demo-household",
          title: "Gezinsafspraak",
          starts_at: new Date(2026, 6, 12, 10, 0) as unknown as string,
          ends_at: null,
          location: null,
          participant_ids: ["demo-user-1"],
        },
      ],
    };

    const insight = buildPeopleWorkloadInsight(data, "2026-07-11T09:00:00.000Z");

    expect(insight.upcomingEvents.map((event) => event.id)).toEqual(["event-1"]);
    expect(insight.memberLoads.find((load) => load.member.user_id === "demo-user-1")?.load).toBe(2);
  });
});
