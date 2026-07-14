import { describe, expect, it } from "vitest";
import { buildEmergencyReadiness, hasContact, hasDocument, hasInfo } from "@/lib/emergency-readiness";
import type { AppData } from "@/lib/types";

const baseData: Pick<AppData, "householdContacts" | "householdInfoItems" | "householdDocuments"> = {
  householdContacts: [],
  householdInfoItems: [],
  householdDocuments: [],
};

describe("emergency readiness", () => {
  it("matches contacts, info and documents case-insensitively", () => {
    const data = {
      householdContacts: [contact({ name: "Huisartsenpost Amsterdam" })],
      householdInfoItems: [info({ title: "Meterkast", value: "Hoofdschakelaar naast de voordeur" })],
      householdDocuments: [documentItem({ title: "Paspoort Fatih" })],
    };

    expect(hasContact(data, "huisarts")).toBe(true);
    expect(hasInfo(data, "meterkast")).toBe(true);
    expect(hasDocument(data, "paspoort")).toBe(true);
  });

  it("builds score and next missing item", () => {
    const readiness = buildEmergencyReadiness({
      householdContacts: [
        contact({ name: "Huisarts", priority: "nood", phone: "010-1234567" }),
        contact({ name: "School", relationship: "school" }),
      ],
      householdInfoItems: [info({ category: "Techniek", is_sensitive: true })],
      householdDocuments: [],
    });

    expect(readiness.doneCount).toBe(3);
    expect(readiness.totalCount).toBe(6);
    expect(readiness.score).toBe(50);
    expect(readiness.criticalContactCount).toBe(1);
    expect(readiness.callableCriticalContactCount).toBe(1);
    expect(readiness.sensitiveItemCount).toBe(1);
    expect(readiness.nextMissing?.id).toBe("buren");
  });

  it("returns complete readiness when all core items exist", () => {
    const readiness = buildEmergencyReadiness({
      householdContacts: [
        contact({ name: "Huisarts", relationship: "huisarts" }),
        contact({ name: "School", relationship: "school" }),
        contact({ name: "Buren sleuteladres", relationship: "buren" }),
      ],
      householdInfoItems: [
        info({ title: "Verzekering", category: "verzekering" }),
        info({ title: "Meterkast", category: "techniek" }),
      ],
      householdDocuments: [documentItem({ title: "Identiteit", category: "identiteit" })],
    });

    expect(readiness.score).toBe(100);
    expect(readiness.nextMissing).toBeNull();
  });
});

function contact(overrides: Partial<AppData["householdContacts"][number]> = {}): AppData["householdContacts"][number] {
  return {
    id: "contact",
    household_id: "hh",
    name: "Contact",
    relationship: null,
    phone: null,
    email: null,
    address: null,
    notes: null,
    priority: "normaal",
    ...overrides,
  };
}

function info(overrides: Partial<AppData["householdInfoItems"][number]> = {}): AppData["householdInfoItems"][number] {
  return {
    id: "info",
    household_id: "hh",
    title: "Info",
    category: "Huis",
    value: null,
    notes: null,
    is_sensitive: false,
    ...overrides,
  };
}

function documentItem(overrides: Partial<AppData["householdDocuments"][number]> = {}): AppData["householdDocuments"][number] {
  return {
    id: "document",
    household_id: "hh",
    title: "Document",
    category: "Algemeen",
    owner_name: null,
    location: null,
    reference: null,
    notes: null,
    expires_at: null,
    is_sensitive: false,
    created_at: "2026-07-11T08:00:00.000Z",
    ...overrides,
  };
}
