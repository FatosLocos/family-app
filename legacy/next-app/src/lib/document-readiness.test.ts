import { describe, expect, it } from "vitest";
import { buildDocumentReadiness } from "@/lib/document-readiness";
import type { AppData } from "@/lib/types";

describe("buildDocumentReadiness", () => {
  it("flags missing location and expiry as next actions", () => {
    const readiness = buildDocumentReadiness({
      householdDocuments: [
        documentItem({ title: "Paspoort", category: "Identiteit", location: null, expires_at: null }),
      ],
    }, "2026-07-11");

    expect(readiness.total).toBe(1);
    expect(readiness.missingLocation).toHaveLength(1);
    expect(readiness.importantWithoutExpiry).toHaveLength(1);
    expect(readiness.nextAction.id).toBe("locations");
  });

  it("counts essential categories and sensitive labels", () => {
    const readiness = buildDocumentReadiness({
      householdDocuments: [
        documentItem({ category: "Identiteit", location: "Kluis", expires_at: "2027-01-01", is_sensitive: true }),
        documentItem({ id: "polis", category: "Verzekering", location: "Map", expires_at: "2026-08-01" }),
        documentItem({ id: "contract", category: "Contract", location: "Cloud", expires_at: "2026-09-01" }),
        documentItem({ id: "garantie", category: "Garantie", location: "Mail", expires_at: "2027-09-01" }),
      ],
    }, "2026-07-11");

    expect(readiness.sensitive).toHaveLength(1);
    expect(readiness.missingEssentials).toEqual(["Medisch"]);
    expect(readiness.expiringQuarter).toHaveLength(2);
    expect(readiness.score).toBe(readiness.totalChecks);
  });

  it("handles Date expiry values from database adapters", () => {
    const readiness = buildDocumentReadiness({
      householdDocuments: [
        documentItem({ id: "paspoort", category: "Identiteit", location: "Kluis", expires_at: new Date(2026, 6, 20) as unknown as string }),
      ],
    }, "2026-07-11");

    expect(readiness.expiringQuarter.map((document) => document.id)).toEqual(["paspoort"]);
  });
});

function documentItem(overrides: Partial<AppData["householdDocuments"][number]> = {}): AppData["householdDocuments"][number] {
  return {
    id: "document",
    household_id: "hh",
    title: "Document",
    category: "Algemeen",
    owner_name: null,
    location: "Map",
    reference: null,
    notes: null,
    expires_at: null,
    is_sensitive: false,
    created_at: "2026-07-11T08:00:00.000Z",
    ...overrides,
  };
}
