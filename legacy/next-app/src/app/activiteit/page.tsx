import Link from "next/link";
import { redirect } from "next/navigation";
import { Activity, Bell, CheckCircle2, Clock3, CircleAlert, Plus, Search } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import type { ActivityItem } from "@/lib/activity";
import { buildActivityInsight } from "@/lib/activity-insights";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { shortDate } from "@/lib/format";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ActivityPage() {
  const now = new Date().toISOString();
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <ActivityContent data={await getLocalAppData()} now={now} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <ActivityContent data={data} now={now} />;
}

function ActivityContent({ data, now }: { data: AppData; now: string }) {
  const insight = buildActivityInsight(data, now, 60);

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Gezinslogboek</span>
          <h1>Activiteit</h1>
          <p className="hero-copy">
            Een tijdlijn van wat er in huis gebeurt: afgeronde taken, nieuwe boodschappen, afspraken, betaalmomenten, onderhoud en documenten.
          </p>
          <div className="quick-actions">
            <Link className="button primary" href="/snel">
              <Plus size={17} /> Snel toevoegen
            </Link>
            <Link className="button" href="/meldingen">
              <Bell size={17} /> Meldingen
            </Link>
            <Link className="button" href="/zoeken">
              <Search size={17} /> Zoeken
            </Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Overzicht</span>
            <h2 style={{ margin: "8px 0 0" }}>{insight.activity.length === 0 ? "Nog geen activiteit" : `${insight.activity.length} signalen`}</h2>
            <p className="muted">Samengesteld uit alle modules van het huishouden.</p>
          </div>
          <div className="today-stack">
            <Metric label="Aankomend" value={insight.upcoming.length} />
            <Metric label="Recent" value={insight.recent.length} />
            <Metric label="Urgent" value={insight.urgent.length} />
          </div>
        </aside>
      </section>

      <section className="activity-control card" style={{ marginTop: 22 }}>
        <div className="section-head">
          <div>
            <span className="eyebrow">Regie</span>
            <h2>Activiteitkwaliteit</h2>
            <p className="muted">Controleer of de tijdlijn actueel, breed gevuld en vrij van urgente achterstand is.</p>
          </div>
          <span className={insight.urgent.length > 0 ? "status accent" : "status"}>
            {insight.score}/{insight.totalChecks} op orde
          </span>
        </div>
        <div className="activity-control-grid">
          <ActivityMetric label="Tijdlijn" value={insight.activity.length} detail={`${insight.moduleCounts.length} modules`} />
          <ActivityMetric label="Aankomend" value={insight.upcoming.length} detail="Planning en deadlines" />
          <ActivityMetric label="Recent" value={insight.recent.length} detail="Wijzigingen en afrondingen" />
          <ActivityMetric label="Urgent" value={insight.urgent.length} detail={insight.urgent[0]?.title ?? "Geen achterstand"} />
        </div>
        <div className="activity-readiness">
          <div>
            <strong>{insight.topSignal ? insight.topSignal.title : "Geen topsignaal"}</strong>
            <span>{insight.percent}% ingericht</span>
          </div>
          <div className="setup-bar" aria-hidden="true">
            <span style={{ width: `${insight.percent}%` }} />
          </div>
        </div>
        <div className="activity-next-row">
          <div>
            <strong>{insight.topSignal ? insight.topSignal.detail : "Gebruik modules om je gezinslogboek te vullen."}</strong>
            <p className="muted">
              {insight.topSignal
                ? `${insight.topSignal.module} · ${shortDate(insight.topSignal.at)}`
                : "Taken, boodschappen, agenda, onderhoud en documenten leveren automatisch signalen."}
            </p>
          </div>
          <div className="activity-module-tags">
            {insight.moduleCounts.slice(0, 5).map((item) => (
              <span className="status" key={item.module}>{item.module}: {item.count}</span>
            ))}
            {insight.moduleCounts.length === 0 && <span className="status">Geen modules</span>}
          </div>
        </div>
        <div className="activity-action-grid">
          {insight.actions.map((action) => (
            <Link className={action.done ? "activity-action done" : "activity-action"} href={action.href} key={action.id}>
              <span>{action.done ? "Op orde" : "Actie"}</span>
              <strong>{action.title}</strong>
              <small>{action.detail}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="grid two-col" style={{ marginTop: 22 }}>
        <div className="card module-card">
          <div className="section-head">
            <div>
              <h2>Aankomend</h2>
              <p className="muted">{insight.attention.length + insight.urgent.length} item{insight.attention.length + insight.urgent.length === 1 ? "" : "s"} vragen aandacht.</p>
            </div>
            <span className="summary-icon">
              <Clock3 size={18} />
            </span>
          </div>
          <ActivityList items={insight.upcoming} empty="Geen aankomende items gevonden." />
        </div>

        <div className="card module-card">
          <div className="section-head">
            <div>
              <h2>Recent</h2>
              <p className="muted">Laatste wijzigingen en verwerkte items.</p>
            </div>
            <span className="summary-icon">
              <Activity size={18} />
            </span>
          </div>
          <ActivityList items={insight.recent} empty="Nog geen recente activiteit." />
        </div>
      </section>
    </AppShell>
  );
}

function ActivityList({ items, empty }: { items: ActivityItem[]; empty: string }) {
  return (
    <ul className="list activity-list">
      {items.length === 0 && <li className="empty-state">{empty}</li>}
      {items.map((item) => (
        <li className={`list-row activity-row ${item.tone}`} key={item.id}>
          <span className="activity-marker" aria-hidden="true">
            {item.tone === "success" ? <CheckCircle2 size={16} /> : item.tone === "urgent" ? <CircleAlert size={16} /> : <Activity size={16} />}
          </span>
          <div className="row-main">
            <div className="row-title">{item.title}</div>
            <div className="row-meta">{item.module} · {shortDate(item.at)}</div>
            <div className="row-description">{item.detail}</div>
          </div>
          <Link className={item.tone === "urgent" ? "status accent" : "status"} href={item.href}>
            Open
          </Link>
        </li>
      ))}
    </ul>
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

function ActivityMetric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="activity-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
