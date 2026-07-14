import { describe, expect, it } from "vitest";
import { buildDataGovernanceInsight } from "@/lib/data-governance";
import { demoData } from "@/lib/demo-data";

describe("buildDataGovernanceInsight", () => {
  it("summarizes modules, integrations and sensitive records", () => {
    const insight = buildDataGovernanceInsight(demoData);

    expect(insight.exportVersion).toBe(3);
    expect(insight.counts.find((item) => item.key === "tasks")?.count).toBe(demoData.tasks.length);
    expect(insight.totalRecords).toBeGreaterThan(0);
    expect(insight.sensitiveTotal).toBe(
      demoData.householdDocuments.filter((item) => item.is_sensitive).length +
        demoData.householdInfoItems.filter((item) => item.is_sensitive).length,
    );
    expect(insight.activeIntegrations).toBeGreaterThan(0);
  });

  it("returns the first missing backup action", () => {
    const insight = buildDataGovernanceInsight({
      ...demoData,
      householdDocuments: demoData.householdDocuments.map((document) => ({ ...document, is_sensitive: false })),
      householdInfoItems: demoData.householdInfoItems.map((item) => ({ ...item, is_sensitive: false })),
      calendarIntegrations: [],
      bankConnections: [],
      taskIntegrations: [],
      smartHomeIntegrations: [],
      hasHomeAssistantConfig: false,
      hasHueConfig: false,
    });

    expect(insight.nextAction?.id).toBe("sensitive-labels");
    expect(insight.backupPercent).toBeLessThan(100);
  });
});
