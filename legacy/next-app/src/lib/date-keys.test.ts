import { describe, expect, it } from "vitest";
import { dateKey, dateSortValue } from "@/lib/date-keys";

describe("date key helpers", () => {
  it("normalizes strings and Date objects to local yyyy-mm-dd keys", () => {
    expect(dateKey("2026-07-11")).toBe("2026-07-11");
    expect(dateKey("2026-07-11T08:30:00.000Z")).toBe("2026-07-11");
    expect(dateKey(new Date(2026, 6, 11))).toBe("2026-07-11");
    expect(dateKey(null)).toBeNull();
  });

  it("sorts missing dates last", () => {
    expect(dateSortValue(null)).toBe(Number.MAX_SAFE_INTEGER);
    expect(dateSortValue("2026-07-11")).toBeLessThan(dateSortValue(null));
  });
});
