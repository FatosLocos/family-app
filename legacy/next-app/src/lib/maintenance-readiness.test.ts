import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildMaintenanceReadiness } from "@/lib/maintenance-readiness";
import type { AppData } from "@/lib/types";

describe("maintenance readiness", () => {
  it("detects overdue work, missing dates, providers and coverage gaps", () => {
    const data: AppData = {
      ...demoData,
      maintenanceItems: [
        {
          id: "smoke",
          household_id: "demo-household",
          title: "Rookmelders testen",
          area: "Veiligheid",
          provider: null,
          due_date: "2026-07-01",
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
        {
          id: "cv",
          household_id: "demo-household",
          title: "CV controleren",
          area: "Techniek",
          provider: null,
          due_date: null,
          frequency: "none",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
    };

    const readiness = buildMaintenanceReadiness(data, "2026-07-11");

    expect(readiness.open).toHaveLength(2);
    expect(readiness.overdue.map((item) => item.id)).toEqual(["smoke"]);
    expect(readiness.withoutDate.map((item) => item.id)).toEqual(["cv"]);
    expect(readiness.withoutProvider.map((item) => item.id)).toEqual(["cv"]);
    expect(readiness.missingEssentialAreas).toEqual(["Tuin"]);
    expect(readiness.actions.find((action) => action.id === "overdue")?.done).toBe(false);
    expect(readiness.actions.find((action) => action.id === "coverage")?.done).toBe(false);
  });

  it("scores a complete maintenance setup", () => {
    const data: AppData = {
      ...demoData,
      maintenanceItems: [
        {
          id: "smoke",
          household_id: "demo-household",
          title: "Rookmelders testen",
          area: "Veiligheid",
          provider: null,
          due_date: "2026-07-15",
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
        {
          id: "cv",
          household_id: "demo-household",
          title: "CV onderhoud",
          area: "Techniek",
          provider: "Installateur",
          due_date: "2026-09-01",
          frequency: "yearly",
          status: "open",
          notes: null,
          completed_at: null,
        },
        {
          id: "garden",
          household_id: "demo-household",
          title: "Dakgoot en tuin",
          area: "Tuin",
          provider: "Hovenier",
          due_date: "2026-08-01",
          frequency: "quarterly",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
    };

    const readiness = buildMaintenanceReadiness(data, "2026-07-11");

    expect(readiness.score).toBe(readiness.totalChecks);
    expect(readiness.percent).toBe(100);
    expect(readiness.thisWeek.map((item) => item.id)).toEqual(["smoke"]);
    expect(readiness.nextItem?.id).toBe("smoke");
    expect(readiness.areaSummaries).toHaveLength(3);
  });

  it("counts Date due dates from local Postgres", () => {
    const data: AppData = {
      ...demoData,
      maintenanceItems: [
        {
          id: "smoke",
          household_id: "demo-household",
          title: "Rookmelders testen",
          area: "Veiligheid",
          provider: null,
          due_date: new Date(2026, 6, 12) as unknown as string,
          frequency: "monthly",
          status: "open",
          notes: null,
          completed_at: null,
        },
      ],
    };

    const readiness = buildMaintenanceReadiness(data, "2026-07-11");

    expect(readiness.thisWeek.map((item) => item.id)).toEqual(["smoke"]);
    expect(readiness.nextItem?.id).toBe("smoke");
  });
});
