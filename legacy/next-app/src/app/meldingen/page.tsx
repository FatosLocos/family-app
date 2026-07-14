import Link from "next/link";
import { redirect } from "next/navigation";
import { Bell, CalendarDays, CircleAlert, Gauge, Info, Mail, Route, TriangleAlert } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { buildNotificationInsight, type NotificationModuleCount } from "@/lib/notification-insights";
import type { NotificationItem } from "@/lib/notifications";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function NotificationsPage() {
  const now = new Date().toISOString();
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <NotificationsContent data={await getLocalAppData()} now={now} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <NotificationsContent data={data} now={now} />;
}

function NotificationsContent({ data, now }: { data: AppData; now: string }) {
  const insight = buildNotificationInsight(data, now);

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Reminders</span>
          <h1>Meldingen</h1>
          <p className="hero-copy">
            Een centrale inbox voor alles wat aandacht vraagt in het huishouden: deadlines, betaalmomenten, onderhoud, documenten en terugkerende boodschappen.
          </p>
          <div className="quick-actions">
            <Link className="button primary" href="/vandaag">Vandaag</Link>
            <Link className="button" href="/snel">Snel toevoegen</Link>
            <Link className="button" href="/instellingen">Meldingvoorkeuren</Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Status</span>
            <h2 style={{ margin: "8px 0 0" }}>{insight.urgent.length > 0 ? `${insight.urgent.length} urgent` : "Geen urgente meldingen"}</h2>
            <p className="muted">Automatisch samengesteld uit alle modules.</p>
          </div>
          <div className="today-stack">
            <Metric label="Totaal" value={insight.notifications.length} />
            <Metric label="Urgent" value={insight.urgent.length} />
            <Metric label="Aandacht" value={insight.attention.length} />
            <Metric label="Info" value={insight.info.length} />
          </div>
        </aside>
      </section>

      <NotificationBriefing
        tone={insight.briefingTone}
        pressureScore={insight.pressureScore}
        topAction={insight.topAction}
        busiestModule={insight.busiestModule}
        todayCount={insight.todayItems.length}
        tomorrowCount={insight.tomorrowItems.length}
        setupCount={insight.setupItems.length}
      />

      <section className="notification-digest card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Dagoverzicht</span>
            <h2>Persoonlijke briefing</h2>
            <p className="muted">Voorbeeld van wat gezinsleden per e-mail of later via push kunnen ontvangen.</p>
          </div>
          <span className={insight.digest.ready ? "status" : "status accent"}>
            {insight.digest.ready ? `${insight.digest.enabledRecipients.length} ontvanger${insight.digest.enabledRecipients.length === 1 ? "" : "s"}` : "Niet klaar"}
          </span>
        </div>
        <div className="notification-digest-grid">
          <div className="notification-digest-main">
            <span className="summary-icon"><Mail size={18} /></span>
            <div>
              <strong>{insight.digest.subject}</strong>
              <p className="muted">
                {insight.digest.nextTime
                  ? `Volgende geplande dagoverzicht: ${insight.digest.nextTime}.`
                  : "Kies in Instellingen eerst een dagoverzicht-tijd voor minimaal een gezinslid."}
              </p>
            </div>
          </div>
          <div className="notification-digest-recipients">
            {insight.digest.recipients.map((recipient) => (
              <span className={recipient.enabled ? "status" : "status accent"} key={recipient.id}>
                {recipient.name}: {recipient.enabled ? recipient.time ?? "geen tijd" : "uit"}
              </span>
            ))}
          </div>
        </div>
        <ul className="list">
          {insight.digest.previewItems.length === 0 && <li className="empty-state">Geen items voor het dagoverzicht.</li>}
          {insight.digest.previewItems.map((item) => (
            <li className={`list-row notification-row ${item.tone}`} key={item.id}>
              <div className="row-main">
                <div className="row-title">{item.title}</div>
                <div className="row-meta">{item.module} · {item.dueLabel}</div>
              </div>
              <Link className="status" href={item.href}>Open</Link>
            </li>
          ))}
        </ul>
        <div className="notification-briefing-actions">
          <Link className="button" href="/instellingen">Voorkeuren aanpassen</Link>
          <Link className="button" href="/vandaag">Dagbeeld openen</Link>
        </div>
      </section>

      <section className="notification-readiness card" style={{ marginTop: 22 }}>
        <div className="section-head">
          <div>
            <span className="eyebrow">Regie</span>
            <h2>Meldingenkwaliteit</h2>
            <p className="muted">Check of de inbox rustig, bruikbaar en over modules verdeeld is.</p>
          </div>
          <span className={insight.quiet ? "status" : "status accent"}>{insight.quiet ? "Rustig" : "Actie"}</span>
        </div>
        <div className="notification-action-grid">
          <NotificationAction title="Geen urgente achterstand" detail={insight.urgent.length === 0 ? "Er zijn geen urgente meldingen" : `${insight.urgent.length} urgente melding${insight.urgent.length === 1 ? "" : "en"}`} href={insight.topAction?.href ?? "/vandaag"} done={insight.urgent.length === 0} />
          <NotificationAction title="Vandaag is inzichtelijk" detail={insight.todayItems.length > 0 ? `${insight.todayItems.length} item${insight.todayItems.length === 1 ? "" : "s"} voor vandaag` : "Geen dagitems, bekijk Vandaag voor rust"} href="/vandaag" done={insight.todayItems.length > 0 || insight.quiet} />
          <NotificationAction title="Setup-signalen beperkt" detail={insight.setupItems.length === 0 ? "Geen setupmeldingen" : `${insight.setupItems.length} inrichtingstaak${insight.setupItems.length === 1 ? "" : "en"} open`} href="/inrichting" done={insight.setupItems.length === 0} />
          <NotificationAction title="Moduledekking" detail={insight.moduleCounts.length > 0 ? `${insight.moduleCounts.length} module${insight.moduleCounts.length === 1 ? "" : "s"} leveren signalen` : "Nog geen modules met meldingen"} href="/koppelingen" done={insight.moduleCounts.length >= 2 || insight.quiet} />
        </div>
      </section>

      <section className="notification-command" style={{ marginTop: 22 }}>
        <div className="card notification-priority-card">
          <div className="section-head">
            <div>
              <span className="eyebrow">Prioriteit</span>
              <h2>Eerstvolgende actie</h2>
            </div>
            <span className="summary-icon"><Bell size={18} /></span>
          </div>
          {insight.topAction ? (
            <Link className={`notification-focus ${insight.topAction.tone}`} href={insight.topAction.href}>
              <div>
                <strong>{insight.topAction.title}</strong>
                <span>{insight.topAction.module} · {insight.topAction.dueLabel}</span>
                <p>{insight.topAction.detail}</p>
              </div>
              <span>Open</span>
            </Link>
          ) : (
            <div className="empty-state">Er zijn geen open meldingen. Alles is rustig.</div>
          )}
          <div className="notification-focus-grid">
            <NotificationMetric label="Te laat" value={insight.overdueItems.length} tone="urgent" />
            <NotificationMetric label="Vandaag" value={insight.todayItems.length} tone="attention" />
            <NotificationMetric label="Morgen" value={insight.tomorrowItems.length} tone="info" />
            <NotificationMetric label="Setup" value={insight.setupItems.length} tone="neutral" />
          </div>
        </div>

        <div className="card notification-agenda-card">
          <div className="section-head">
            <div>
              <span className="eyebrow">Dagplanning</span>
              <h2>Vandaag en morgen</h2>
            </div>
            <span className="summary-icon"><CalendarDays size={18} /></span>
          </div>
          <NotificationMiniList title="Vandaag" items={insight.todayItems} empty="Geen meldingen voor vandaag." />
          <NotificationMiniList title="Morgen" items={insight.tomorrowItems} empty="Geen meldingen voor morgen." />
        </div>

        <div className="card notification-module-card">
          <div className="section-head">
            <div>
              <span className="eyebrow">Verdeling</span>
              <h2>Per module</h2>
            </div>
          </div>
          <div className="notification-module-grid">
            {insight.moduleCounts.map((item) => (
              <Link className="notification-module-pill" href={moduleHref(item.module)} key={item.module}>
                <span>{item.module}</span>
                <strong>{item.count}</strong>
              </Link>
            ))}
            {insight.moduleCounts.length === 0 && <div className="empty-state">Geen modules met meldingen.</div>}
          </div>
        </div>
      </section>

      <section className="grid three-col" style={{ marginTop: 22 }}>
        <NotificationGroup title="Urgent" icon={<CircleAlert size={18} />} items={insight.urgent} empty="Geen verlopen of urgente items." />
        <NotificationGroup title="Aandacht" icon={<TriangleAlert size={18} />} items={insight.attention} empty="Geen items die binnenkort aandacht vragen." />
        <NotificationGroup title="Info" icon={<Info size={18} />} items={insight.info} empty="Geen informatieve meldingen." />
      </section>
    </AppShell>
  );
}

function NotificationBriefing({
  tone,
  pressureScore,
  topAction,
  busiestModule,
  todayCount,
  tomorrowCount,
  setupCount,
}: {
  tone: NotificationItem["tone"];
  pressureScore: number;
  topAction: NotificationItem | null;
  busiestModule: NotificationModuleCount | null;
  todayCount: number;
  tomorrowCount: number;
  setupCount: number;
}) {
  const title = tone === "urgent" ? "Er is directe actie nodig" : tone === "attention" ? "Er zijn aandachtspunten" : "Het huishouden is rustig";
  const detail = topAction
    ? `${topAction.module}: ${topAction.title}`
    : setupCount > 0
      ? "Maak de inrichting verder af voor rijkere meldingen."
      : "Geen open signalen uit de gekoppelde modules.";

  return (
    <section className={`notification-briefing card ${tone}`}>
      <div className="notification-briefing-main">
        <span className="summary-icon">
          <Gauge size={18} />
        </span>
        <div>
          <span className="eyebrow">Dagbriefing</span>
          <h2>{title}</h2>
          <p className="muted">{detail}</p>
        </div>
      </div>
      <div className="notification-briefing-grid">
        <BriefingMetric label="Drukte" value={`${pressureScore}%`} detail={pressureScore >= 70 ? "Hoog" : pressureScore >= 30 ? "Gemiddeld" : "Rustig"} />
        <BriefingMetric label="Vandaag" value={todayCount} detail={`${tomorrowCount} morgen`} />
        <BriefingMetric label="Topmodule" value={busiestModule?.module ?? "Geen"} detail={busiestModule ? `${busiestModule.count} melding${busiestModule.count === 1 ? "" : "en"}` : "Geen signalen"} />
      </div>
      <div className="notification-briefing-actions">
        <Link className={tone === "urgent" ? "button primary" : "button"} href={topAction?.href ?? "/inrichting"}>
          <Route size={17} /> {topAction ? "Open beste actie" : "Inrichting openen"}
        </Link>
        <Link className="button" href="/vandaag">Vandaag</Link>
      </div>
    </section>
  );
}

function BriefingMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="briefing-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function NotificationGroup({ title, icon, items, empty }: { title: string; icon: React.ReactNode; items: NotificationItem[]; empty: string }) {
  return (
    <div className="card module-card">
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          <p className="muted">{items.length} melding{items.length === 1 ? "" : "en"}</p>
        </div>
        <span className="summary-icon">{icon}</span>
      </div>
      <ul className="list">
        {items.length === 0 && <li className="empty-state">{empty}</li>}
        {items.map((item) => (
          <li className={`list-row notification-row ${item.tone}`} key={item.id}>
            <div className="row-main">
              <div className="row-title">{item.title}</div>
              <div className="row-meta">{item.module} · {item.dueLabel}</div>
              <div className="row-description">{item.detail}</div>
            </div>
            <Link className="status" href={item.href}>
              Open
            </Link>
          </li>
        ))}
      </ul>
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

function NotificationMetric({ label, value, tone }: { label: string; value: number; tone: "urgent" | "attention" | "info" | "neutral" }) {
  return (
    <div className={`notification-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function NotificationAction({ title, detail, href, done }: { title: string; detail: string; href: string; done: boolean }) {
  return (
    <Link className={done ? "notification-action done" : "notification-action"} href={href}>
      <span>{done ? "Op orde" : "Actie"}</span>
      <strong>{title}</strong>
      <small>{detail}</small>
    </Link>
  );
}

function NotificationMiniList({ title, items, empty }: { title: string; items: NotificationItem[]; empty: string }) {
  return (
    <div className="notification-mini-list">
      <div className="row-title">{title}</div>
      <ul>
        {items.length === 0 && <li className="muted">{empty}</li>}
        {items.slice(0, 4).map((item) => (
          <li key={item.id}>
            <Link href={item.href}>
              <span>{item.module}</span>
              <strong>{item.title}</strong>
            </Link>
          </li>
        ))}
        {items.length > 4 && <li className="muted">+{items.length - 4} meer</li>}
      </ul>
    </div>
  );
}

function moduleHref(module: NotificationItem["module"]) {
  const hrefs: Record<NotificationItem["module"], string> = {
    Taken: "/taken",
    Agenda: "/agenda",
    Boodschappen: "/boodschappen",
    Geld: "/geld",
    Documenten: "/documenten",
    Onderhoud: "/onderhoud",
    Prikbord: "/prikbord",
    Instellingen: "/instellingen",
  };
  return hrefs[module];
}
