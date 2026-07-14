import Link from "next/link";
import { redirect } from "next/navigation";
import { AlertTriangle, FileText, Home, Mail, MapPin, Navigation, Phone, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { buildEmergencyReadiness } from "@/lib/emergency-readiness";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { shortDate } from "@/lib/format";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData, HouseholdContact, HouseholdDocument, HouseholdInfoItem } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function EmergencyPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <EmergencyContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <EmergencyContent data={data} />;
}

function EmergencyContent({ data }: { data: AppData }) {
  const emergencyContacts = [...data.householdContacts].sort(contactSort);
  const emergencyInfo = data.householdInfoItems
    .filter((item) => ["nood", "medisch", "huis", "verzekering", "school", "techniek"].includes(item.category.toLowerCase()))
    .slice(0, 8);
  const importantDocuments = data.householdDocuments
    .filter((document) => ["identiteit", "verzekering", "contract", "garantie", "medisch"].includes(document.category.toLowerCase()) || document.expires_at)
    .slice(0, 8);
  const readiness = buildEmergencyReadiness(data);
  const nextMissing = readiness.nextMissing;
  const callableContacts = emergencyContacts.filter((contact) => contact.phone).slice(0, 4);
  const firstAddress = emergencyContacts.find((contact) => contact.address)?.address ?? emergencyInfo.find((item) => /adres|locatie|huis/i.test(`${item.title} ${item.category}`) && item.value)?.value ?? null;

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel emergency-hero">
          <span className="eyebrow">Snel bij de hand</span>
          <h1>Noodkaart</h1>
          <p className="hero-copy">
            Belangrijke contacten en huisinformatie op een plek voor situaties waarin je geen tijd wilt verliezen.
          </p>
          <div className="quick-actions">
            <Link className="button primary" href="/gezin">Contact toevoegen</Link>
            <Link className="button" href="/documenten">Document toevoegen</Link>
            <Link className="button" href="/instellingen">Gezinsleden beheren</Link>
          </div>
        </div>
        <aside className="today-panel emergency-panel">
          <div>
            <span className="eyebrow">Nood</span>
            <h2 style={{ margin: "8px 0 0" }}>112</h2>
            <p className="muted">Bel direct bij levensgevaar, brand of acute nood.</p>
          </div>
          <div className="today-stack">
            <EmergencyCall label="112 bellen" href="tel:112" />
            <EmergencyCall label="Huisarts zoeken" href="/gezin" />
          </div>
        </aside>
      </section>

      <section className="emergency-action-strip card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Direct handelen</span>
            <h2>Bel of navigeer zonder zoeken</h2>
            <p className="muted">De belangrijkste noodacties staan hier bovenaan, met één tik bereikbaar.</p>
          </div>
          <span className={readiness.callableCriticalContactCount > 0 ? "status" : "status accent"}>
            {readiness.callableCriticalContactCount} belbaar
          </span>
        </div>
        <div className="emergency-action-grid">
          <a className="emergency-action-card urgent" href="tel:112">
            <Phone size={18} />
            <strong>112 bellen</strong>
            <small>Levensgevaar, brand of acute nood</small>
          </a>
          {callableContacts.map((contact) => (
            <a className="emergency-action-card" href={`tel:${contact.phone}`} key={contact.id}>
              <Phone size={18} />
              <strong>{contact.name}</strong>
              <small>{[contact.relationship, contact.phone].filter(Boolean).join(" · ")}</small>
            </a>
          ))}
          {firstAddress ? (
            <a className="emergency-action-card" href={`https://maps.apple.com/?q=${encodeURIComponent(firstAddress)}`}>
              <Navigation size={18} />
              <strong>Route openen</strong>
              <small>{firstAddress}</small>
            </a>
          ) : (
            <Link className="emergency-action-card attention" href="/gezin">
              <MapPin size={18} />
              <strong>Adres ontbreekt</strong>
              <small>Voeg huisadres of sleuteladres toe</small>
            </Link>
          )}
        </div>
      </section>

      <section className="emergency-control card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Noodregie</span>
            <h2>Noodkaart compleetheid</h2>
            <p className="muted">Zorg dat iedereen snel dezelfde contact-, huis- en documentinformatie kan vinden.</p>
          </div>
          <span className={readiness.doneCount < readiness.totalCount ? "status accent" : "status"}>
            {readiness.doneCount}/{readiness.totalCount} compleet
          </span>
        </div>
        <div className="emergency-control-grid">
          <EmergencyMetric icon={<Phone size={17} />} label="Noodcontacten" value={readiness.criticalContactCount} detail={`${emergencyContacts.length} contacten totaal`} />
          <EmergencyMetric icon={<Home size={17} />} label="Huisinfo" value={emergencyInfo.length} detail="Techniek, verzekering, school of medisch" />
          <EmergencyMetric icon={<FileText size={17} />} label="Documenten" value={importantDocuments.length} detail="Belangrijke referenties en vervaldata" />
          <EmergencyMetric icon={<ShieldCheck size={17} />} label="Gevoelig" value={readiness.sensitiveItemCount} detail="Afgeschermd in lijsten en zoekresultaten" />
        </div>
        <div className="emergency-readiness">
          <div>
            <strong>Noodkaart-score</strong>
            <span>{readiness.score}% ingericht</span>
          </div>
          <div className="setup-bar" aria-hidden="true">
            <span style={{ width: `${readiness.score}%` }} />
          </div>
        </div>
        <div className="emergency-next-row">
          <div>
            <strong>{nextMissing ? nextMissing.label : "Noodkaart is compleet genoeg voor dagelijks gebruik"}</strong>
            <p className="muted">
              {nextMissing ? "Vul dit aan om de noodkaart betrouwbaarder te maken." : "Controleer periodiek of nummers, locaties en documenten nog actueel zijn."}
            </p>
          </div>
          <Link className="button" href={nextMissing?.href ?? "/documenten"}>{nextMissing ? "Aanvullen" : "Controleren"}</Link>
        </div>
      </section>

      <section className="grid two-col" style={{ marginTop: 22 }}>
        <div className="grid">
          <EmergencyCard icon={<Phone size={18} />} title="Belangrijke contacten" count={emergencyContacts.length}>
            <ul className="list">
              {emergencyContacts.length === 0 && <li className="empty-state">Nog geen contacten. Voeg huisarts, school, buren of oppas toe via Gezin.</li>}
              {emergencyContacts.map((contact) => (
                <ContactRow contact={contact} key={contact.id} />
              ))}
            </ul>
          </EmergencyCard>

          <EmergencyCard icon={<Home size={18} />} title="Huisinformatie" count={emergencyInfo.length}>
            <ul className="list">
              {emergencyInfo.length === 0 && <li className="empty-state">Nog geen nood- of huisinformatie opgeslagen.</li>}
              {emergencyInfo.map((item) => (
                <InfoRow item={item} key={item.id} />
              ))}
            </ul>
          </EmergencyCard>
        </div>

        <div className="grid">
          <EmergencyCard icon={<FileText size={18} />} title="Belangrijke documenten" count={importantDocuments.length}>
            <ul className="list">
              {importantDocuments.length === 0 && <li className="empty-state">Nog geen belangrijke documenten of referenties opgeslagen.</li>}
              {importantDocuments.map((document) => (
                <DocumentRow document={document} key={document.id} />
              ))}
            </ul>
          </EmergencyCard>

          <div className="card emergency-checklist">
            <div className="section-head">
              <div>
                <h2>Checklist</h2>
                <p className="muted">Informatie die deze kaart sterker maakt.</p>
              </div>
              <span className="summary-icon">
                <AlertTriangle size={18} />
              </span>
            </div>
            <ul className="list">
              {readiness.items.map((item) => (
                <ChecklistItem done={item.done} label={item.label} href={item.href} key={item.id} />
              ))}
            </ul>
          </div>
        </div>
      </section>
    </AppShell>
  );
}

function EmergencyMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="emergency-metric">
      <span className="emergency-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function EmergencyCard({ icon, title, count, children }: { icon: React.ReactNode; title: string; count: number; children: React.ReactNode }) {
  return (
    <div className="card module-card">
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          <p className="muted">{count} item{count === 1 ? "" : "s"} beschikbaar.</p>
        </div>
        <span className="summary-icon">{icon}</span>
      </div>
      {children}
    </div>
  );
}

function ContactRow({ contact }: { contact: HouseholdContact }) {
  return (
    <li className="list-row">
      <div className="row-main">
        <div className="row-title">{contact.name}</div>
        <div className="row-meta">{[contact.relationship, priorityLabel(contact.priority)].filter(Boolean).join(" · ")}</div>
        {contact.notes && <div className="row-description">{contact.notes}</div>}
        <div className="contact-actions">
          {contact.phone && (
            <a className="icon-link" href={`tel:${contact.phone}`}>
              <Phone size={15} />
              <span>{contact.phone}</span>
            </a>
          )}
          {contact.email && (
            <a className="icon-link" href={`mailto:${contact.email}`}>
              <Mail size={15} />
              <span>{contact.email}</span>
            </a>
          )}
          {contact.address && (
            <span className="icon-link">
              <MapPin size={15} />
              <span>{contact.address}</span>
            </span>
          )}
        </div>
      </div>
      <span className={contact.priority === "nood" ? "status accent" : "status"}>{priorityLabel(contact.priority)}</span>
    </li>
  );
}

function InfoRow({ item }: { item: HouseholdInfoItem }) {
  return (
    <li className="list-row">
      <div className="row-main">
        <div className="row-title">{item.title}</div>
        <div className="row-meta">{item.category}</div>
        {item.value && <div className="row-description">{item.is_sensitive ? "Gevoelige informatie opgeslagen" : item.value}</div>}
        {item.notes && <div className="row-meta">{item.notes}</div>}
      </div>
      {item.is_sensitive && <span className="status accent">Gevoelig</span>}
    </li>
  );
}

function DocumentRow({ document }: { document: HouseholdDocument }) {
  return (
    <li className="list-row">
      <div className="row-main">
        <div className="row-title">{document.title}</div>
        <div className="row-meta">
          {[document.category, document.owner_name, document.expires_at ? `vervalt ${shortDate(document.expires_at)}` : null].filter(Boolean).join(" · ")}
        </div>
        {document.location && <div className="row-description">Bewaarplek: {document.location}</div>}
        {document.reference && <div className="row-meta">Referentie: {document.is_sensitive ? "Gevoelige referentie opgeslagen" : document.reference}</div>}
      </div>
      {document.is_sensitive && <span className="status accent">Gevoelig</span>}
    </li>
  );
}

function ChecklistItem({ done, label, href }: { done: boolean; label: string; href: string }) {
  return (
    <li className="list-row">
      <div className="row-main">
        <div className="row-title">{label}</div>
        <div className="row-meta">{done ? "Ingevuld" : "Nog aanvullen"}</div>
      </div>
      <Link className={done ? "status" : "status accent"} href={href}>{done ? "OK" : "Aanvullen"}</Link>
    </li>
  );
}

function EmergencyCall({ label, href }: { label: string; href: string }) {
  return (
    <Link className="emergency-call" href={href}>
      {label}
    </Link>
  );
}

function contactSort(a: HouseholdContact, b: HouseholdContact) {
  return priorityScore(a.priority) - priorityScore(b.priority) || a.name.localeCompare(b.name);
}

function priorityScore(priority: string) {
  if (priority === "nood") return 0;
  if (priority === "belangrijk") return 1;
  return 2;
}

function priorityLabel(priority: string) {
  if (priority === "nood") return "Nood";
  if (priority === "belangrijk") return "Belangrijk";
  return "Normaal";
}
