import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildBulletinInsight } from "@/lib/bulletin-insights";
import type { AppData } from "@/lib/types";

describe("bulletin insights", () => {
  it("detects expired notes, short content and missing pinned notes", () => {
    const data: AppData = {
      ...demoData,
      householdNotes: [
        {
          id: "note-1",
          household_id: "demo-household",
          title: "Oud bericht",
          body: "Kort",
          category: "Huis",
          pinned: false,
          expires_at: "2026-07-01",
          created_by: "demo-user-1",
          created_at: "2026-06-30T10:00:00.000Z",
        },
      ],
    };

    const insight = buildBulletinInsight(data, "2026-07-11");

    expect(insight.total).toBe(1);
    expect(insight.expired.map((note) => note.id)).toEqual(["note-1"]);
    expect(insight.emptyBody.map((note) => note.id)).toEqual(["note-1"]);
    expect(insight.actions.find((action) => action.id === "pinned")?.done).toBe(false);
    expect(insight.nextAction.id).toBe("pinned");
  });

  it("scores a complete bulletin setup", () => {
    const data: AppData = {
      ...demoData,
      householdNotes: [
        {
          id: "note-1",
          household_id: "demo-household",
          title: "School ophalen",
          body: "Vrijdag haalt Fatih de kinderen op bij school.",
          category: "School",
          pinned: true,
          expires_at: "2026-07-13",
          created_by: "demo-user-1",
          created_at: "2026-07-10T10:00:00.000Z",
        },
        {
          id: "note-2",
          household_id: "demo-household",
          title: "Afval",
          body: "Groene bak moet donderdagavond aan de straat.",
          category: "Huis",
          pinned: false,
          expires_at: "2026-07-16",
          created_by: "demo-user-2",
          created_at: "2026-07-09T10:00:00.000Z",
        },
      ],
    };

    const insight = buildBulletinInsight(data, "2026-07-11");

    expect(insight.score).toBe(insight.totalChecks);
    expect(insight.percent).toBe(100);
    expect(insight.expiring).toHaveLength(2);
    expect(insight.categories).toEqual(["Huis", "School"]);
    expect(insight.nextAction.done).toBe(true);
  });

  it("handles Date expiry values from database adapters", () => {
    const data: AppData = {
      ...demoData,
      householdNotes: [
        {
          id: "note-1",
          household_id: "demo-household",
          title: "School ophalen",
          body: "Vrijdag haalt Fatih de kinderen op bij school.",
          category: "School",
          pinned: false,
          expires_at: new Date(2026, 6, 13) as unknown as string,
          created_by: "demo-user-1",
          created_at: "2026-07-10T10:00:00.000Z",
        },
        {
          id: "note-2",
          household_id: "demo-household",
          title: "Oude reminder",
          body: "Deze mag naar verlopen berichten.",
          category: "Huis",
          pinned: false,
          expires_at: new Date(2026, 6, 1) as unknown as string,
          created_by: "demo-user-1",
          created_at: "2026-07-01T10:00:00.000Z",
        },
      ],
    };

    const insight = buildBulletinInsight(data, "2026-07-11");

    expect(insight.expiring.map((note) => note.id)).toEqual(["note-1"]);
    expect(insight.expired.map((note) => note.id)).toEqual(["note-2"]);
  });
});
