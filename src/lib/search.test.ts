import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildSearchResults } from "@/lib/search";

describe("buildSearchResults", () => {
  it("finds finance items by title", () => {
    const results = buildSearchResults(demoData, "hypotheek");
    expect(results.some((result) => result.module === "Geld" && result.title === "Hypotheek")).toBe(true);
  });

  it("finds sensitive documents by safe metadata without exposing references", () => {
    const results = buildSearchResults(demoData, "identiteit");
    const document = results.find((result) => result.id === "document-document-1");
    expect(document?.detail).toContain("Gevoelige referentie verborgen");
    expect(document?.detail).not.toContain("Paspoort");
    expect(document?.privacy).toBe("masked");
  });

  it("does not match sensitive document references or household info values", () => {
    const data = {
      ...demoData,
      householdDocuments: [
        {
          ...demoData.householdDocuments[0],
          id: "sensitive-document",
          title: "Identiteitsbewijs",
          category: "Identiteit",
          reference: "SECRET-PASSPORT-123",
          is_sensitive: true,
        },
      ],
      householdInfoItems: [
        {
          ...demoData.householdInfoItems[0],
          id: "sensitive-info",
          title: "Alarmcode",
          category: "Veiligheid",
          value: "ALARM-9999",
          is_sensitive: true,
        },
      ],
    };

    expect(buildSearchResults(data, "SECRET-PASSPORT-123")).toHaveLength(0);
    expect(buildSearchResults(data, "ALARM-9999")).toHaveLength(0);
    expect(buildSearchResults(data, "Identiteit").some((result) => result.id === "document-sensitive-document")).toBe(true);
    expect(buildSearchResults(data, "Veiligheid").some((result) => result.id === "info-sensitive-info")).toBe(true);
  });

  it("matches accents and casing loosely", () => {
    const results = buildSearchResults(demoData, "GARANTIE");
    expect(results.some((result) => result.title === "Garantie wasmachine")).toBe(true);
  });
});
