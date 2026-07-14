import { describe, expect, it } from "vitest";
import { memberName, money, shortDate } from "@/lib/format";

describe("format helpers", () => {
  it("formats cents as Dutch euro amounts", () => {
    expect(money(12345)).toBe("€ 123,45");
  });

  it("returns a useful fallback for missing dates", () => {
    expect(shortDate(null)).toBe("Geen datum");
  });

  it("resolves member names with fallbacks", () => {
    const members = [
      { user_id: "1", profile: { full_name: "Fatih", email: "fatih@example.com" } },
      { user_id: "2", profile: { full_name: null, email: "gezin@example.com" } },
    ];

    expect(memberName("1", members)).toBe("Fatih");
    expect(memberName("2", members)).toBe("gezin@example.com");
    expect(memberName("3", members)).toBe("Gezinslid");
    expect(memberName(null, members)).toBe("Niet toegewezen");
  });
});
