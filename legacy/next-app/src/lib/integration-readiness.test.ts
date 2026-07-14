import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildIntegrationReadiness } from "@/lib/integration-readiness";

describe("buildIntegrationReadiness", () => {
  it("summarizes configured integrations and domains", () => {
    const readiness = buildIntegrationReadiness(demoData);

    expect(readiness.total).toBe(7);
    expect(readiness.cards.map((card) => card.id)).toContain("outlook");
    expect(readiness.domains.find((domain) => domain.label === "Smart home")?.total).toBe(3);
    expect(readiness.configured).toBeGreaterThan(0);
  });

  it("prioritizes sync errors before missing integrations", () => {
    const readiness = buildIntegrationReadiness({
      ...demoData,
      calendarIntegrations: [{ ...demoData.calendarIntegrations[0], status: "sync_error" }],
      bankConnections: [],
      taskIntegrations: [],
      hasHomeAssistantConfig: false,
      hasHueConfig: false,
      smartHomeIntegrations: [],
    });

    expect(readiness.nextAttention?.id).toBe("outlook");
    expect(readiness.attention).toBe(1);
    expect(readiness.missing).toBeGreaterThan(0);
  });

  it("reports missing status when no integrations are configured", () => {
    const readiness = buildIntegrationReadiness({
      ...demoData,
      calendarIntegrations: [],
      bankConnections: [],
      taskIntegrations: [],
      hasHomeAssistantConfig: false,
      hasHueConfig: false,
      smartHomeIntegrations: [],
    });

    expect(readiness.configured).toBe(0);
    expect(readiness.missing).toBe(7);
    expect(readiness.percent).toBe(0);
  });
});
