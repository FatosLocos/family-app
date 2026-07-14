import Link from "next/link";
import { redirect } from "next/navigation";
import { Activity, AlertTriangle, CalendarDays, CheckCircle2, Home, Landmark, ListChecks, PlugZap, Settings } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { shortDate } from "@/lib/format";
import { buildIntegrationReadiness, type IntegrationCardData, type IntegrationStatus } from "@/lib/integration-readiness";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function IntegrationsPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <IntegrationsContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <IntegrationsContent data={data} />;
}

function IntegrationsContent({ data }: { data: AppData }) {
  const readiness = buildIntegrationReadiness(data);

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Systeemstatus</span>
          <h1>Koppelingen</h1>
          <p className="hero-copy">
            Een centrale plek voor externe diensten en apparaten: agenda, bank, taken-apps en smart home.
          </p>
          <div className="quick-actions">
            <Link className="button primary" href="/instellingen">Koppeling instellen</Link>
            <Link className="button" href="/agenda">Agenda</Link>
            <Link className="button" href="/geld">Geld</Link>
            <Link className="button" href="/home">Home</Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Status</span>
            <h2 style={{ margin: "8px 0 0" }}>{readiness.configured} actief</h2>
            <p className="muted">{readiness.attention} koppeling{readiness.attention === 1 ? "" : "en"} vragen aandacht.</p>
          </div>
          <div className="today-stack">
            <Metric label="Actief" value={readiness.configured} />
            <Metric label="Aandacht" value={readiness.attention} />
            <Metric label="Totaal" value={readiness.total} />
          </div>
        </aside>
      </section>

      <section className="integration-control card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Integratieregie</span>
            <h2>Wat is gekoppeld en wat mist nog?</h2>
            <p className="muted">Status per domein, syncsignalen en de eerstvolgende configuratieactie.</p>
          </div>
          <span className="summary-icon">
            <Settings size={18} />
          </span>
        </div>
        <div className="integration-control-grid">
          <IntegrationMetric icon={<CheckCircle2 size={17} />} label="Actief" value={readiness.configured} detail={`${readiness.total} koppelingen totaal`} />
          <IntegrationMetric icon={<AlertTriangle size={17} />} label="Aandacht" value={readiness.attention} detail={readiness.nextAttention?.title ?? "Geen actieve fouten"} />
          <IntegrationMetric icon={<PlugZap size={17} />} label="Niet gekoppeld" value={readiness.missing} detail={`${readiness.planned} gepland of voorbereid`} />
          <IntegrationMetric icon={<Activity size={17} />} label="Laatste sync" value={readiness.latestSync?.lastSync ? shortDate(readiness.latestSync.lastSync) : "Geen"} detail={readiness.latestSync?.title ?? "Nog geen synchistorie"} />
        </div>
        <div className="integration-domain-grid">
          {readiness.domains.map((group) => (
            <Link className="integration-domain" href={group.cards.find((card) => card.status !== "configured")?.href ?? "/koppelingen"} key={group.label}>
              <div>
                <strong>{group.label}</strong>
                <span>{group.active} van {group.total} actief</span>
              </div>
              <div className="setup-bar" aria-hidden="true">
                <span style={{ width: `${group.percent}%` }} />
              </div>
            </Link>
          ))}
        </div>
        {readiness.nextAttention && (
          <div className="integration-next-row">
            <div>
              <strong>{readiness.nextAttention.title}</strong>
              <p className="muted">{readiness.nextAttention.detail}</p>
            </div>
            <Link className="button primary" href={readiness.nextAttention.href}>
              Open configuratie
            </Link>
          </div>
        )}
        <div className="integration-action-grid">
          {readiness.cards.map((card) => (
            <Link className={card.status === "configured" ? "integration-action done" : "integration-action"} href={card.href} key={card.id}>
              <span>{statusLabel(card.status)}</span>
              <strong>{card.title}</strong>
              <small>{integrationActionDetail(card)}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="grid integrations-grid" style={{ marginTop: 22 }}>
        {readiness.cards.map((card) => (
          <Link className={`card interactive integration-card ${card.status}`} href={card.href} key={card.id}>
            <div className="section-head">
              <div>
                <h2>{card.title}</h2>
                <p className="muted">{card.module}</p>
              </div>
              <span className="summary-icon">{iconForIntegration(card.id)}</span>
            </div>
            <p>{card.detail}</p>
            <div className="integration-footer">
              <span className={statusClass(card.status)}>{statusLabel(card.status)}</span>
              <small>{card.lastSync ? `Sync ${shortDate(card.lastSync)}` : "Geen sync bekend"}</small>
            </div>
          </Link>
        ))}
      </section>
    </AppShell>
  );
}

function IntegrationMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="integration-metric">
      <span className="integration-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="today-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function statusLabel(status: IntegrationStatus) {
  if (status === "configured") return "Actief";
  if (status === "needs_auth") return "Login nodig";
  if (status === "needs_session") return "Sessie nodig";
  if (status === "sync_error") return "Sync fout";
  if (status === "planned") return "Gepland";
  return "Niet gekoppeld";
}

function statusClass(status: IntegrationStatus) {
  if (status === "configured") return "status";
  if (status === "needs_auth" || status === "needs_session" || status === "sync_error") return "status accent";
  return "status";
}

function integrationActionDetail(card: IntegrationCardData) {
  if (card.status === "configured") return card.lastSync ? `Laatst gesynchroniseerd ${shortDate(card.lastSync)}` : "Koppeling is actief.";
  if (card.status === "sync_error") return "Controleer autorisatie of serverbereikbaarheid.";
  if (card.status === "needs_auth") return "Rond de OAuth/autorisatie af.";
  if (card.status === "needs_session") return "Maak de provider-sessie af.";
  if (card.status === "planned") return "Voorbereid, nog niet live gekoppeld.";
  return card.detail;
}

function iconForIntegration(id: string) {
  if (id === "outlook") return <CalendarDays size={18} />;
  if (id === "bunq") return <Landmark size={18} />;
  if (id === "tasks") return <ListChecks size={18} />;
  if (id === "home-assistant") return <Home size={18} />;
  if (id === "hue") return <PlugZap size={18} />;
  return <Activity size={18} />;
}
