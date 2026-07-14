import Link from "next/link";
import { redirect } from "next/navigation";
import { Building2, CalendarDays, Download, Mail, MapPinned, Phone, Trash2, Upload, UserRound, UsersRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { AddressBookContactForm, AddressBookImportForm, AddressBookMemberForm } from "@/components/forms";
import { ModuleLayout } from "@/components/module-layout";
import { ModuleSubmenu } from "@/components/module-submenu";
import { deleteAddressBookMember, deleteHouseholdContact } from "@/app/actions";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import type { AppData, HouseholdContact } from "@/lib/types";

export const dynamic = "force-dynamic";

type AddressBookSearchParams = {
  q?: string;
  type?: string;
  imported?: string;
};

export default async function AddressBookPage({ searchParams }: { searchParams?: Promise<AddressBookSearchParams> }) {
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="instellingen" />;
  const user = await getLocalUser();
  if (!user) redirect("/login");
  return <AddressBookContent data={await getLocalAppData()} searchParams={await searchParams} />;
}

function AddressBookContent({ data, searchParams }: { data: AppData; searchParams?: AddressBookSearchParams }) {
  const query = searchParams?.q?.trim().toLocaleLowerCase("nl-NL") ?? "";
  const type = contactTypeFilter(searchParams?.type);
  const members = data.householdContactMembers ?? [];
  const contacts = data.householdContacts.filter((contact) => {
    if (type !== "alles" && contact.contact_type !== type) return false;
    if (!query) return true;
    const contactMembers = members.filter((member) => member.contact_id === contact.id);
    return [
      contact.name,
      contact.relationship,
      contact.phone,
      contact.email,
      contact.address,
      contact.city,
      contactMembers.map((member) => `${member.name} ${member.relationship ?? ""}`).join(" "),
    ].filter(Boolean).join(" ").toLocaleLowerCase("nl-NL").includes(query);
  });
  const birthdayMembers = members.filter((member) => member.birth_date).length;
  const familyContacts = data.householdContacts.filter((contact) => contact.contact_type === "gezin");
  const familyCount = familyContacts.length;

  return (
    <AppShell>
      <ModuleLayout
        asideLabel="Adresboekacties"
        aside={<>
          <ModuleSubmenu title="Contact toevoegen" detail="Persoon, gezin of organisatie centraal opslaan"><AddressBookContactForm /></ModuleSubmenu>
          {familyContacts.length > 0 && <ModuleSubmenu title="Persoon aan familie toevoegen" detail="Zoek een familie en voeg een persoon met geboortedatum toe"><AddressBookMemberForm contacts={familyContacts} /></ModuleSubmenu>}
          <ModuleSubmenu title="Contacten importeren" detail="vCard of CSV vanuit een andere app inlezen"><AddressBookImportForm /></ModuleSubmenu>
          <Link className="module-submenu-collapsed" href="/api/adresboek/export" title="Contacten als vCard exporteren">
            <span className="module-submenu-trigger"><span className="summary-icon"><Download size={15} /></span><span><strong>Contacten exporteren</strong><small>Download een vCard-bestand</small></span></span>
          </Link>
        </>}
      >
        <div className="grid">
          <CompactModuleHeader
            eyebrow="Huis"
            title="Adresboek"
            stats={[
              { label: "contacten", value: data.householdContacts.length },
              { label: "gezinnen", value: familyCount },
              { label: "verjaardagen", value: birthdayMembers },
            ]}
          >
            Familie, vrienden, buren en belangrijke organisaties op een plek.
          </CompactModuleHeader>
          {searchParams?.imported && <p className="status">{searchParams.imported} contact{Number(searchParams.imported) === 1 ? "" : "en"} verwerkt.</p>}
          <AddressBookFilters query={searchParams?.q ?? ""} type={type} />
          <section className="addressbook-list" aria-label="Contacten">
            {contacts.length === 0 && <div className="card empty-state">Geen contacten gevonden met deze selectie.</div>}
            {contacts.map((contact) => <AddressBookContactCard contact={contact} members={members.filter((member) => member.contact_id === contact.id)} key={contact.id} />)}
          </section>
        </div>
      </ModuleLayout>
    </AppShell>
  );
}

function AddressBookFilters({ query, type }: { query: string; type: ContactTypeFilter }) {
  return (
    <form className="addressbook-filters" method="get" data-instant-search>
      <label className="sr-only" htmlFor="addressbook-search">Contacten zoeken</label>
      <input id="addressbook-search" name="q" defaultValue={query} placeholder="Zoek naam, familie, plaats of relatie" />
      <select aria-label="Type contact" name="type" defaultValue={type}>
        <option value="alles">Alle contacten</option>
        <option value="persoon">Personen</option>
        <option value="gezin">Gezinnen en families</option>
        <option value="organisatie">Organisaties</option>
      </select>
      <button className="button" type="submit">Filter</button>
    </form>
  );
}

function AddressBookContactCard({ contact, members }: { contact: HouseholdContact; members: NonNullable<AppData["householdContactMembers"]> }) {
  const address = contactAddress(contact);
  const mapsHref = address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}` : null;
  const Icon = contact.contact_type === "gezin" ? UsersRound : contact.contact_type === "organisatie" ? Building2 : UserRound;
  return (
    <article className="addressbook-contact card">
      <div className="addressbook-contact-head">
        <span className="summary-icon"><Icon size={18} /></span>
        <div>
          <span className="eyebrow">{contactTypeLabel(contact.contact_type)}</span>
          <h2>{contact.name}</h2>
          <p className="muted">{[contact.relationship, priorityLabel(contact.priority)].filter(Boolean).join(" · ") || "Contact"}</p>
        </div>
        <form action={deleteHouseholdContact}>
          <input type="hidden" name="id" value={contact.id} />
          <button className="icon-button" title="Contact verwijderen" aria-label={`${contact.name} verwijderen`}><Trash2 size={17} /></button>
        </form>
      </div>
      {(contact.phone || contact.email || address) && <div className="addressbook-contact-actions">
        {contact.phone && <a className="icon-link" href={`tel:${contact.phone}`}><Phone size={15} /><span>{contact.phone}</span></a>}
        {contact.email && <a className="icon-link" href={`mailto:${contact.email}`}><Mail size={15} /><span>{contact.email}</span></a>}
        {mapsHref && <a className="icon-link" href={mapsHref} target="_blank" rel="noreferrer" title="Open adres in Maps"><MapPinned size={15} /><span>{address}</span></a>}
      </div>}
      {contact.notes && <p className="addressbook-notes">{contact.notes}</p>}
      <div className="addressbook-members">
        <div className="addressbook-members-head"><strong>Leden</strong><span>{members.length}</span></div>
        {members.length === 0 && <p className="muted">Nog geen leden toegevoegd.</p>}
        {members.map((member) => (
          <div className="addressbook-member" key={member.id}>
            <div>
              <strong>{member.name}</strong>
              <span>{[member.relationship, member.birth_date ? `jarig ${birthdayLabel(member.birth_date)}` : null].filter(Boolean).join(" · ")}</span>
            </div>
            <div className="addressbook-member-actions">
              {member.phone && <a href={`tel:${member.phone}`} aria-label={`${member.name} bellen`} title="Bellen"><Phone size={14} /></a>}
              {member.email && <a href={`mailto:${member.email}`} aria-label={`${member.name} mailen`} title="Mailen"><Mail size={14} /></a>}
              <form action={deleteAddressBookMember}>
                <input type="hidden" name="id" value={member.id} />
                <button type="submit" aria-label={`${member.name} verwijderen`} title="Lid verwijderen"><Trash2 size={14} /></button>
              </form>
            </div>
          </div>
        ))}
      </div>
      {members.some((member) => member.birth_date) && <div className="addressbook-birthday-note"><CalendarDays size={15} /> Verjaardagen zijn opgenomen in Agenda.</div>}
    </article>
  );
}

type ContactTypeFilter = "alles" | "persoon" | "gezin" | "organisatie";

function contactTypeFilter(value: string | undefined): ContactTypeFilter {
  return value === "persoon" || value === "gezin" || value === "organisatie" ? value : "alles";
}

function contactTypeLabel(type: HouseholdContact["contact_type"]) {
  if (type === "gezin") return "Gezin of familie";
  if (type === "organisatie") return "Organisatie";
  return "Persoon";
}

function priorityLabel(priority: HouseholdContact["priority"]) {
  if (priority === "nood") return "Noodcontact";
  if (priority === "belangrijk") return "Belangrijk";
  return "Normaal";
}

function contactAddress(contact: HouseholdContact) {
  return [contact.address, [contact.postal_code, contact.city].filter(Boolean).join(" "), contact.country].filter(Boolean).join(", ");
}

function birthdayLabel(value: string) {
  return new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "short" }).format(new Date(`${value}T12:00:00.000Z`));
}
