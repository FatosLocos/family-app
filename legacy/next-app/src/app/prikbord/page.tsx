import { redirect } from "next/navigation";
import Link from "next/link";
import { Bell, MessageSquare, Pin, Plus, Timer } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { HouseholdNoteForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { HouseholdNoteList } from "@/components/module-lists";
import { buildBulletinInsight } from "@/lib/bulletin-insights";
import { demoData } from "@/lib/demo-data";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { shortDate } from "@/lib/format";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function BulletinPage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <BulletinContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <BulletinContent data={data} />;
}

function BulletinContent({ data, demo = false }: { data: typeof demoData; demo?: boolean }) {
  const today = new Date().toISOString().slice(0, 10);
  const insight = buildBulletinInsight(data, today);

  return (
    <AppShell demo={demo}>
      <section className="grid two-col">
        <div className="grid">
          <CompactModuleHeader
            eyebrow="Dagelijks"
            title="Prikbord"
            stats={[
              { label: "berichten", value: insight.total },
              { label: "vastgezet", value: insight.pinnedNotes.length },
              { label: "loopt af", value: insight.expiring.length },
              { label: "aandacht", value: insight.attentionCount },
              { label: "categorieen", value: insight.categories.length },
            ]}
          >
            Korte gezinsberichten, tijdelijke notities en vastgezette mededelingen.
          </CompactModuleHeader>
          <HouseholdNoteList data={data} readOnly={demo} />
        </div>
        <div className="grid">
          {demo ? (
            <DemoPanel />
          ) : (
            <ModuleSubmenu title="Bericht plaatsen" detail="Korte gezinsnotitie op het prikbord zetten">
              <HouseholdNoteForm />
            </ModuleSubmenu>
          )}
        </div>
      </section>
    </AppShell>
  );
}

function BulletinControlPanel({ data, today }: { data: AppData; today: string }) {
  const insight = buildBulletinInsight(data, today);
  const highlighted = insight.pinnedNotes[0] ?? insight.latest;

  return (
    <section className="bulletin-control card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Gezinsprikbord</span>
          <h2>Wat moet blijven hangen?</h2>
          <p className="muted">Vastgezette berichten, tijdelijke notities en categorieën in één overzicht.</p>
        </div>
        <span className="summary-icon">
          <MessageSquare size={18} />
        </span>
      </div>
      <div className="bulletin-control-grid">
        <BulletinMetric icon={<Pin size={17} />} label="Vastgezet" value={insight.pinnedNotes.length} detail="Altijd bovenaan zichtbaar" />
        <BulletinMetric icon={<Timer size={17} />} label="Loopt af" value={insight.expiring.length} detail="Binnen 7 dagen" />
        <BulletinMetric icon={<Bell size={17} />} label="Aandacht" value={insight.attentionCount} detail={`${insight.expired.length} verlopen`} />
        <BulletinMetric icon={<MessageSquare size={17} />} label="Categorieën" value={insight.categories.length} detail={insight.categories.slice(0, 2).join(", ") || "Nog geen"} />
      </div>
      <div className="bulletin-readiness">
        <div>
          <strong>Prikbord op orde</strong>
          <span>{insight.score}/{insight.totalChecks} punten op orde</span>
        </div>
        <div className="setup-bar" aria-hidden="true">
          <span style={{ width: `${insight.percent}%` }} />
        </div>
      </div>
      <div className="bulletin-next-row">
        <div>
          <strong>{highlighted?.title ?? insight.nextAction.title}</strong>
          <p className="muted">
            {highlighted
              ? `${highlighted.category} · ${highlighted.pinned ? "vastgezet" : `geplaatst ${shortDate(highlighted.created_at)}`}${highlighted.expires_at ? ` · tot ${shortDate(highlighted.expires_at)}` : ""}`
              : insight.nextAction.detail}
          </p>
          <div className="tag-list">
            {insight.expiring.slice(0, 6).map((note) => (
              <span className="tag" key={note.id}>{note.title}</span>
            ))}
            {insight.expiring.length === 0 && <span className="muted">Geen berichten die deze week aflopen.</span>}
          </div>
        </div>
        <div className="bulletin-action-stack">
          <Link className="button primary" href="/snel">
            <Plus size={17} /> Snel bericht
          </Link>
          <Link className="button" href="/vandaag">Vandaag</Link>
        </div>
      </div>
      <div className="bulletin-action-grid">
        {insight.actions.map((action) => (
          <Link className={action.done ? "bulletin-action done" : "bulletin-action"} href={action.href} key={action.id}>
            <span>{action.done ? "Op orde" : "Actie"}</span>
            <strong>{action.title}</strong>
            <small>{action.detail}</small>
          </Link>
        ))}
      </div>
    </section>
  );
}

function BulletinMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="bulletin-metric">
      <span className="bulletin-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Log in met een databaseconfiguratie om gezinsberichten lokaal te bewaren.</p>
    </div>
  );
}
