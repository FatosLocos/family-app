import type { AppData } from "@/lib/types";

export type EmergencyReadinessItem = {
  id: string;
  done: boolean;
  label: string;
  href: string;
  group: "contact" | "info" | "document";
};

export type EmergencyReadiness = {
  items: EmergencyReadinessItem[];
  doneCount: number;
  totalCount: number;
  score: number;
  missing: EmergencyReadinessItem[];
  nextMissing: EmergencyReadinessItem | null;
  criticalContactCount: number;
  callableCriticalContactCount: number;
  sensitiveItemCount: number;
};

export function buildEmergencyReadiness(
  data: Pick<AppData, "householdContacts" | "householdInfoItems" | "householdDocuments">,
): EmergencyReadiness {
  const items: EmergencyReadinessItem[] = [
    { id: "huisarts", done: hasContact(data, "huisarts") || hasContact(data, "huisartsenpost"), label: "Huisarts of huisartsenpost", href: "/gezin", group: "contact" },
    { id: "school", done: hasContact(data, "school") || hasContact(data, "opvang"), label: "School of opvang", href: "/gezin", group: "contact" },
    { id: "buren", done: hasContact(data, "buren") || hasContact(data, "buur") || hasContact(data, "sleutel"), label: "Buren of sleuteladres", href: "/gezin", group: "contact" },
    { id: "verzekering", done: hasInfo(data, "verzekering") || hasDocument(data, "verzekering") || hasDocument(data, "polis"), label: "Verzekering of polisinfo", href: "/gezin", group: "info" },
    { id: "techniek", done: hasInfo(data, "techniek") || hasInfo(data, "meterkast") || hasInfo(data, "afsluiter"), label: "Meterkast, afsluiters of techniek", href: "/gezin", group: "info" },
    { id: "identiteit", done: hasDocument(data, "identiteit") || hasDocument(data, "paspoort") || hasDocument(data, "id-kaart"), label: "Identiteitsdocumenten", href: "/documenten", group: "document" },
  ];
  const doneCount = items.filter((item) => item.done).length;
  const sensitiveInfoCount = data.householdInfoItems.filter((item) => item.is_sensitive).length;
  const sensitiveDocumentCount = data.householdDocuments.filter((document) => document.is_sensitive).length;
  const missing = items.filter((item) => !item.done);

  return {
    items,
    doneCount,
    totalCount: items.length,
    score: Math.round((doneCount / items.length) * 100),
    missing,
    nextMissing: missing[0] ?? null,
    criticalContactCount: data.householdContacts.filter((contact) => contact.priority === "nood").length,
    callableCriticalContactCount: data.householdContacts.filter((contact) => contact.priority === "nood" && Boolean(contact.phone)).length,
    sensitiveItemCount: sensitiveInfoCount + sensitiveDocumentCount,
  };
}

export function hasContact(data: Pick<AppData, "householdContacts">, term: string) {
  const needle = normalize(term);
  return data.householdContacts.some((contact) =>
    [contact.name, contact.relationship, contact.notes].filter(Boolean).some((value) => normalize(value).includes(needle)),
  );
}

export function hasInfo(data: Pick<AppData, "householdInfoItems">, term: string) {
  const needle = normalize(term);
  return data.householdInfoItems.some((item) =>
    [item.title, item.category, item.value, item.notes].filter(Boolean).some((value) => normalize(value).includes(needle)),
  );
}

export function hasDocument(data: Pick<AppData, "householdDocuments">, term: string) {
  const needle = normalize(term);
  return data.householdDocuments.some((document) =>
    [document.title, document.category, document.owner_name, document.reference, document.notes].filter(Boolean).some((value) => normalize(value).includes(needle)),
  );
}

function normalize(value: string | null | undefined) {
  return String(value ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}
