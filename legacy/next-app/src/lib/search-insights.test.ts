import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildSearchInsight } from "@/lib/search-insights";

describe("search insights", () => {
  it("builds module counts and applies an active filter", () => {
    const insight = buildSearchInsight(demoData, "huis", "Gezin");

    expect(insight.results.length).toBeGreaterThan(0);
    expect(insight.activeModule).toBe("Gezin");
    expect(insight.filteredResults.every((result) => result.module === "Gezin")).toBe(true);
    expect(insight.moduleCounts.length).toBeGreaterThan(1);
    expect(insight.bestResult?.module).toBe("Gezin");
  });

  it("keeps empty queries calm and suggests actions", () => {
    const insight = buildSearchInsight(demoData, "");

    expect(insight.results).toHaveLength(0);
    expect(insight.activeModule).toBe("alles");
    expect(insight.actions.find((action) => action.id === "query")?.done).toBe(false);
    expect(insight.actions.find((action) => action.id === "privacy")?.done).toBe(true);
    expect(insight.suggestedQueries.length).toBeGreaterThan(0);
  });

  it("falls back to all modules for an unavailable filter", () => {
    const insight = buildSearchInsight(demoData, "hypotheek", "Taken");

    expect(insight.activeModule).toBe("alles");
    expect(insight.bestResult?.module).toBe("Geld");
    expect(insight.searchState).toContain("resultaat");
  });
});
