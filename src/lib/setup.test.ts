import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildSetupOverview, setupProgress } from "@/lib/setup";

describe("setupProgress", () => {
  it("calculates progress percentage", () => {
    const progress = setupProgress([
      { id: "a", title: "A", detail: "", href: "/", done: true, group: "Basis" },
      { id: "b", title: "B", detail: "", href: "/", done: false, group: "Basis" },
    ]);

    expect(progress).toEqual({ done: 1, total: 2, percent: 50 });
  });
});

describe("buildSetupOverview", () => {
  it("groups setup steps and reports a next action", () => {
    const overview = buildSetupOverview(demoData);

    expect(overview.steps.length).toBeGreaterThan(10);
    expect(overview.groupProgress.map((item) => item.group)).toContain("Basis");
    expect(overview.progress.total).toBe(overview.steps.length);
    expect(overview.nextAction?.done).not.toBe(true);
  });

  it("prioritizes high impact basis steps before optional integrations", () => {
    const overview = buildSetupOverview({
      ...demoData,
      members: [demoData.members[0]],
      householdContacts: [],
      tasks: [],
      shoppingItems: [],
      shoppingProducts: [],
      calendarIntegrations: [],
      calendarEvents: [],
      hasHomeAssistantConfig: false,
      hasHueConfig: false,
      smartHomeIntegrations: [],
      bankConnections: [],
      financeItems: [],
    });

    expect(overview.highImpactOpen.map((step) => step.id)).toContain("members");
    expect(overview.nextAction?.priority).toBe("hoog");
    expect(overview.nextAction?.group).toBe("Basis");
  });
});
