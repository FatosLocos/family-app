import { redirect } from "next/navigation";
import Link from "next/link";
import { Archive, CalendarClock, FolderOpen, MapPin, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { HouseholdDocumentForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { HouseholdDocumentList } from "@/components/module-lists";
import { demoData } from "@/lib/demo-data";
import { buildDocumentReadiness } from "@/lib/document-readiness";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { getAppData, getUser } from "@/lib/local-data";
import { dateKey, dateSortValue } from "@/lib/date-keys";
import { shortDate } from "@/lib/format";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <DocumentsContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <DocumentsContent data={data} />;
}

function DocumentsContent({ data, demo = false }: { data: typeof demoData; demo?: boolean }) {
  const today = dateKey(new Date()) ?? new Date().toISOString().slice(0, 10);
  const expiring = data.householdDocuments.filter((document) => {
    const expiresAt = dateKey(document.expires_at);
    return expiresAt && expiresAt >= today;
  }).length;

  return (
    <AppShell demo={demo}>
      <section className="grid two-col">
        <div className="grid">
          <div className="page-heading">
            <h1>Documenten</h1>
            <p className="muted">
              {data.householdDocuments.length} documenten · {expiring} met vervaldatum
            </p>
          </div>
          <DocumentControlPanel data={data} today={today} />
          <DocumentVaultPanel data={data} today={today} />
          <HouseholdDocumentList data={data} readOnly={demo} />
        </div>
        <div className="grid">
          {demo ? (
            <DemoPanel />
          ) : (
            <ModuleSubmenu title="Document toevoegen" detail="Document, locatie en vervaldatum opslaan">
              <HouseholdDocumentForm />
            </ModuleSubmenu>
          )}
        </div>
      </section>
    </AppShell>
  );
}

function DocumentVaultPanel({ data, today }: { data: AppData; today: string }) {
  const readiness = buildDocumentReadiness(data, today);

  return (
    <section className="document-vault card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Kluis</span>
          <h2>Documentkluis</h2>
          <p className="muted">Maak belangrijke documenten vindbaar, compleet en veilig gelabeld.</p>
        </div>
        <span className={readiness.score < readiness.totalChecks ? "status accent" : "status"}>{readiness.score}/{readiness.totalChecks} compleet</span>
      </div>
      <div className="document-vault-grid">
        <VaultMetric icon={<Archive size={17} />} label="Compleet" value={readiness.completeDocuments} detail="Met bewaarlocatie en relevante datum" />
        <VaultMetric icon={<MapPin size={17} />} label="Mist plek" value={readiness.missingLocation.length} detail="Geen fysieke of digitale locatie" />
        <VaultMetric icon={<CalendarClock size={17} />} label="90 dagen" value={readiness.expiringQuarter.length} detail="Vervalt binnen 3 maanden" />
        <VaultMetric icon={<ShieldCheck size={17} />} label="Essentieel mist" value={readiness.missingEssentials.length} detail={readiness.missingEssentials.slice(0, 2).join(", ") || "Alles aanwezig"} />
      </div>
      <div className="document-readiness">
        <div>
          <strong>Kluisgereedheid</strong>
          <span>{readiness.percent}% ingericht</span>
        </div>
        <div className="setup-bar" aria-hidden="true">
          <span style={{ width: `${readiness.percent}%` }} />
        </div>
      </div>
      <div className="document-next-action">
        <div>
          <strong>{readiness.nextAction.title}</strong>
          <p className="muted">{readiness.nextAction.detail}</p>
        </div>
        <Link className="button" href={readiness.nextAction.href}>{readiness.nextAction.done ? "Backup bekijken" : "Aanvullen"}</Link>
      </div>
      <div className="document-action-grid">
        {readiness.actions.map((action) => (
          <Link className={action.done ? "document-action done" : "document-action"} href={action.href} key={action.id}>
            <span>{action.done ? "OK" : "Actie"}</span>
            <strong>{action.title}</strong>
            <small>{action.detail}</small>
          </Link>
        ))}
      </div>
    </section>
  );
}

function DocumentControlPanel({ data, today }: { data: AppData; today: string }) {
  const nextMonth = addDays(today, 30);
  const expired = data.householdDocuments.filter((document) => {
    const expiresAt = dateKey(document.expires_at);
    return expiresAt && expiresAt < today;
  });
  const expiringSoon = data.householdDocuments.filter((document) => {
    const expiresAt = dateKey(document.expires_at);
    return expiresAt && expiresAt >= today && expiresAt <= nextMonth;
  });
  const sensitive = data.householdDocuments.filter((document) => document.is_sensitive);
  const withLocation = data.householdDocuments.filter((document) => document.location);
  const nextExpiry = [...data.householdDocuments]
    .filter((document) => document.expires_at)
    .sort((a, b) => dateSortValue(a.expires_at) - dateSortValue(b.expires_at))[0];
  const categories = Object.entries(
    data.householdDocuments.reduce<Record<string, number>>((groups, document) => {
      groups[document.category] = (groups[document.category] ?? 0) + 1;
      return groups;
    }, {}),
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="document-control card">
      <div className="section-head">
        <div>
          <h2>Documentstatus</h2>
          <p className="muted">Vervaldata, gevoelige stukken en vindbaarheid.</p>
        </div>
        <span className={expired.length > 0 ? "status accent" : "status"}>{expired.length} verlopen</span>
      </div>
      <div className="document-control-grid">
        <DocumentMetric label="Totaal" value={data.householdDocuments.length} />
        <DocumentMetric label="Binnenkort" value={expiringSoon.length} />
        <DocumentMetric label="Gevoelig" value={sensitive.length} />
        <DocumentMetric label="Bewaarplek" value={withLocation.length} />
      </div>
      <div className="document-next-row">
        <div>
          <strong>Eerstvolgende vervaldatum</strong>
          <p className="muted">{nextExpiry ? `${nextExpiry.title} · ${shortDate(nextExpiry.expires_at)}` : "Geen vervaldatums vastgelegd."}</p>
        </div>
        <div className="document-categories">
          {categories.length === 0 ? (
            <span className="status">Geen categorieën</span>
          ) : (
            categories.map(([category, count]) => (
              <span className="status" key={category}>
                {category}: {count}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function DocumentMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="document-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function VaultMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: number; detail: string }) {
  return (
    <div className="document-vault-metric">
      <span className="document-vault-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Log in met een databaseconfiguratie om documenten lokaal te beheren.</p>
    </div>
  );
}
