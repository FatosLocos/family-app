import { describe, expect, it } from "vitest";
import { buildStarterPack, buildStarterPackSummary } from "@/lib/starter-pack";

describe("buildStarterPack", () => {
  it("covers the core household modules with useful defaults", () => {
    const pack = buildStarterPack("2026-07-11");

    expect(pack.contacts.some((contact) => contact.priority === "nood")).toBe(true);
    expect(pack.householdInfoItems).toHaveLength(3);
    expect(pack.tasks.some((task) => task.recurrence === "weekly")).toBe(true);
    expect(pack.shoppingProducts.every((product) => product.recurrence === "weekly" || product.recurrence === "monthly")).toBe(true);
    expect(pack.financeBudgets.map((budget) => budget.category)).toContain("Boodschappen");
    expect(pack.financeItems.every((item) => item.status === "gepland")).toBe(true);
    expect(pack.maintenanceItems.some((item) => item.frequency === "monthly")).toBe(true);
    expect(pack.documents.length).toBeGreaterThanOrEqual(3);
    expect(pack.notes[0].pinned).toBe(true);
    expect(pack.mealPlans[0].title).toBe("Weekmenu invullen");
  });

  it("uses relative dates for the starter planning", () => {
    const pack = buildStarterPack("2026-07-11");

    expect(pack.tasks.find((task) => task.title === "Afval controleren")?.due_date).toBe("2026-07-12");
    expect(pack.tasks.find((task) => task.title === "Weekplanning doornemen")?.due_date).toBe("2026-07-13");
    expect(pack.financeItems.find((item) => item.title === "Huur of hypotheek")?.due_date).toBe("2026-08-01");
    expect(pack.notes[0].expires_at).toBe("2026-07-25");
  });

  it("summarizes starter content and follow-up edits", () => {
    const pack = buildStarterPack("2026-07-11");
    const summary = buildStarterPackSummary(pack);

    expect(summary.totalItems).toBeGreaterThan(20);
    expect(summary.modules.map((module) => module.id)).toEqual([
      "contacts",
      "house",
      "tasks",
      "shopping",
      "finance",
      "maintenance",
      "documents",
      "notes",
      "meals",
    ]);
    expect(summary.modules.find((module) => module.id === "finance")?.count).toBe(pack.financeBudgets.length + pack.financeItems.length);
    expect(summary.nextEdits.map((edit) => edit.href)).toEqual(["/geld", "/gezin", "/documenten"]);
  });
});
