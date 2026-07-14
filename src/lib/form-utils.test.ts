import { describe, expect, it } from "vitest";
import { centsFromEuros, centsFromText, internalRedirectPath } from "@/lib/form-utils";

describe("form utils", () => {
  it("parses euro inputs into cents", () => {
    expect(centsFromEuros("12,34")).toBe(1234);
    expect(centsFromEuros("12.34")).toBe(1234);
    expect(centsFromEuros("0")).toBe(0);
  });

  it("rejects invalid money inputs", () => {
    expect(centsFromEuros(null)).toBeNull();
    expect(centsFromEuros("-1")).toBeNull();
    expect(centsFromEuros("niet geldig")).toBeNull();
  });

  it("extracts euro amounts from quick-add text", () => {
    expect(centsFromText("schoolfoto €12,50")).toBe(1250);
    expect(centsFromText("12.95 lunchgeld")).toBe(1295);
    expect(centsFromText("geen bedrag")).toBeNull();
  });

  it("keeps redirects inside the app", () => {
    expect(internalRedirectPath("/invite/ABC123")).toBe("/invite/ABC123");
    expect(internalRedirectPath("https://example.com")).toBe("/");
    expect(internalRedirectPath("//example.com")).toBe("/");
    expect(internalRedirectPath(null)).toBe("/");
  });
});
