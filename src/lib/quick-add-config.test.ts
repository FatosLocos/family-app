import { describe, expect, it } from "vitest";
import { getQuickAddKindConfig, quickAddKindConfigs } from "@/lib/quick-add-config";

describe("quick add config", () => {
  it("covers all supported quick-add kinds", () => {
    expect(quickAddKindConfigs.map((item) => item.value)).toEqual(["task", "shopping", "note", "event", "meal", "finance"]);
  });

  it("only shows type-specific fields where they are useful", () => {
    expect(getQuickAddKindConfig("task").showPriority).toBe(true);
    expect(getQuickAddKindConfig("note").showPinned).toBe(true);
    expect(getQuickAddKindConfig("note").showExpires).toBe(true);
    expect(getQuickAddKindConfig("shopping").dateLabel).toBeNull();
    expect(getQuickAddKindConfig("finance").detailsPlaceholder).toContain("12,50");
  });

  it("falls back to tasks for unknown input", () => {
    expect(getQuickAddKindConfig("unknown").value).toBe("task");
  });
});
