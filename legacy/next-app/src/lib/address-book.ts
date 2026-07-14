import type { HouseholdContact, HouseholdContactMember } from "@/lib/types";

export type ImportedAddressBookContact = {
  name: string;
  relationship?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  postalCode?: string | null;
  city?: string | null;
  country?: string | null;
  notes?: string | null;
  birthDate?: string | null;
};

export function parseAddressBookFile(source: string, filename: string): ImportedAddressBookContact[] {
  if (/\.vcf$/i.test(filename) || /BEGIN:VCARD/i.test(source)) return parseVCard(source);
  return parseCsv(source);
}

export function exportAddressBookVCard(contacts: HouseholdContact[], members: HouseholdContactMember[]) {
  const cards = contacts.flatMap((contact) => {
    const contactMembers = members.filter((member) => member.contact_id === contact.id);
    const root = vCardForContact(contact);
    const people = contactMembers.map((member) => vCardForMember(contact, member));
    return [root, ...people];
  });
  return `${cards.join("\r\n")}\r\n`;
}

function parseVCard(source: string): ImportedAddressBookContact[] {
  const cards = source
    .replace(/\r\n[ \t]/g, "")
    .replace(/\n[ \t]/g, "")
    .split(/BEGIN:VCARD/i)
    .slice(1)
    .map((part) => part.split(/END:VCARD/i)[0] ?? "");

  return cards.flatMap((card) => {
    const fields = new Map<string, string>();
    for (const line of card.split(/\r?\n/)) {
      const separator = line.indexOf(":");
      if (separator < 0) continue;
      const key = line.slice(0, separator).split(";", 1)[0]?.toUpperCase();
      const field = unescapeVCard(line.slice(separator + 1));
      if (key && field && !fields.has(key)) fields.set(key, field);
    }
    const name = fields.get("FN") ?? fields.get("N");
    if (!name) return [];
    const addressParts = (fields.get("ADR") ?? "").split(";");
    return [{
      name: name.replace(/;/g, " ").trim(),
      phone: fields.get("TEL") ?? null,
      email: fields.get("EMAIL") ?? null,
      address: addressParts[2] ?? null,
      city: addressParts[3] ?? null,
      postalCode: addressParts[5] ?? null,
      country: addressParts[6] ?? null,
      notes: fields.get("NOTE") ?? null,
      birthDate: normalizeBirthDate(fields.get("BDAY")),
    }];
  });
}

function parseCsv(source: string): ImportedAddressBookContact[] {
  const rows = csvRows(source);
  const header = rows.shift()?.map(normalizeHeader) ?? [];
  if (header.length === 0) return [];
  return rows.flatMap((row) => {
    const value = (...keys: string[]) => {
      const index = header.findIndex((key) => keys.includes(key));
      return index >= 0 ? row[index]?.trim() || null : null;
    };
    const name = value("naam", "name", "full_name", "display_name");
    if (!name) return [];
    return [{
      name,
      relationship: value("relatie", "relationship", "relation"),
      phone: value("telefoon", "phone", "telephone", "mobile"),
      email: value("email", "e_mail", "mail"),
      address: value("adres", "address", "street", "straat"),
      postalCode: value("postcode", "postal_code", "zip"),
      city: value("plaats", "city", "woonplaats"),
      country: value("land", "country"),
      notes: value("notitie", "notes", "note"),
      birthDate: normalizeBirthDate(value("geboortedatum", "birth_date", "birthday", "bday")),
    }];
  });
}

function csvRows(source: string) {
  const delimiter = source.includes(";") && !source.includes(",") ? ";" : ",";
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === '"') {
      if (quoted && source[index + 1] === '"') {
        value += '"';
        index += 1;
      } else quoted = !quoted;
    } else if (character === delimiter && !quoted) {
      row.push(value);
      value = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && source[index + 1] === "\n") index += 1;
      row.push(value);
      if (row.some((cell) => cell.trim())) rows.push(row);
      row = [];
      value = "";
    } else value += character;
  }
  row.push(value);
  if (row.some((cell) => cell.trim())) rows.push(row);
  return rows;
}

function vCardForContact(contact: HouseholdContact) {
  return vCard({
    name: contact.name,
    phone: contact.phone,
    email: contact.email,
    address: contact.address,
    postalCode: contact.postal_code,
    city: contact.city,
    country: contact.country,
    notes: contact.notes,
    group: contact.contact_type === "gezin" ? "Gezin/familie" : undefined,
  });
}

function vCardForMember(contact: HouseholdContact, member: HouseholdContactMember) {
  return vCard({
    name: member.name,
    phone: member.phone,
    email: member.email,
    address: contact.address,
    postalCode: contact.postal_code,
    city: contact.city,
    country: contact.country,
    notes: member.notes,
    birthDate: member.birth_date,
    group: contact.name,
  });
}

function vCard(input: {
  name: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  postalCode?: string | null;
  city?: string | null;
  country?: string | null;
  notes?: string | null;
  birthDate?: string | null;
  group?: string;
}) {
  const lines = ["BEGIN:VCARD", "VERSION:3.0", `FN:${escapeVCard(input.name)}`];
  if (input.phone) lines.push(`TEL:${escapeVCard(input.phone)}`);
  if (input.email) lines.push(`EMAIL:${escapeVCard(input.email)}`);
  if (input.address || input.postalCode || input.city || input.country) {
    lines.push(`ADR:;;${escapeVCard(input.address ?? "")};${escapeVCard(input.city ?? "")};;${escapeVCard(input.postalCode ?? "")};${escapeVCard(input.country ?? "")}`);
  }
  if (input.birthDate) lines.push(`BDAY:${input.birthDate}`);
  if (input.group) lines.push(`X-FAMILY-APP-GROUP:${escapeVCard(input.group)}`);
  if (input.notes) lines.push(`NOTE:${escapeVCard(input.notes)}`);
  lines.push("END:VCARD");
  return lines.join("\r\n");
}

function normalizeHeader(value: string) {
  return value.trim().toLowerCase().replace(/^\ufeff/, "").replace(/[\s-]+/g, "_");
}

function normalizeBirthDate(value: string | null | undefined) {
  if (!value) return null;
  const compact = value.replace(/[^0-9]/g, "");
  if (compact.length === 8) return `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}`;
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

function escapeVCard(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/;/g, "\\;").replace(/,/g, "\\,");
}

function unescapeVCard(value: string) {
  return value.replace(/\\n/gi, "\n").replace(/\\([,;\\])/g, "$1");
}
