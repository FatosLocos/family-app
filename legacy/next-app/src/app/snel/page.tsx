import Link from "next/link";
import { redirect } from "next/navigation";
import { CalendarDays, CheckSquare, Landmark, MessageSquare, Plus, ShoppingBasket, Utensils, Zap } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { QuickAddForm, QuickPresetGrid } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { demoData } from "@/lib/demo-data";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { buildQuickAddInsight } from "@/lib/quick-add-insights";
import { getAppData, getUser } from "@/lib/local-data";

export const dynamic = "force-dynamic";

export default async function QuickAddPage({
  searchParams,
}: {
  searchParams?: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <QuickAddContent data={await getLocalAppData()} error={params?.error} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <QuickAddContent data={data} error={params?.error} />;
}

function QuickAddContent({ data, error, demo = false }: { data: typeof demoData; error?: string; demo?: boolean }) {
  const today = new Date().toISOString().slice(0, 10);
  const insight = buildQuickAddInsight(data, today);

  return (
    <AppShell demo={demo}>
      <section className="grid two-col">
        <div className="grid">
          <div>
            <span className="eyebrow">Snel vastleggen</span>
            <h1>Snelle invoer</h1>
            <p className="muted">
              Voeg direct iets toe zonder eerst de juiste module te openen. Na opslaan kom je automatisch op de plek waar het item staat.
            </p>
          </div>
          <section className="quick-control card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Commandocentrum</span>
                <h2>Wat kun je nu het snelst vastleggen?</h2>
                <p className="muted">Gebaseerd op open taken, boodschappen, prikbord, agenda en maaltijden.</p>
              </div>
              <span className="summary-icon">
                <Zap size={18} />
              </span>
            </div>
            <div className="quick-control-grid">
              <QuickMetric icon={<CheckSquare size={17} />} label="Taken open" value={insight.openTasks} detail={`${insight.dueToday} vandaag`} />
              <QuickMetric icon={<ShoppingBasket size={17} />} label="Boodschappen" value={insight.openShopping} detail="Open items" />
              <QuickMetric icon={<MessageSquare size={17} />} label="Prikbord" value={insight.pinnedNotes} detail="Vastgezette berichten" />
              <QuickMetric icon={<CalendarDays size={17} />} label="Planning" value={insight.upcomingPlanning} detail="Afspraken en maaltijden" />
            </div>
            <div className="quick-readiness">
              <div>
                <strong>Snelle invoer dekking</strong>
                <span>{insight.score}/{insight.totalChecks} soorten op orde</span>
              </div>
              <div className="setup-bar" aria-hidden="true">
                <span style={{ width: `${insight.percent}%` }} />
              </div>
            </div>
            <div className="quick-suggestion-row">
              <div>
                <strong>{insight.suggestedTitle}</strong>
                <p className="muted">
                  {insight.suggestedDetail}
                </p>
              </div>
              <Link className="button primary" href="/vandaag">
                <Plus size={17} /> Dagbeeld
              </Link>
            </div>
            <div className="quick-action-grid">
              {insight.actions.map((action) => (
                <Link className={action.done ? "quick-action done" : "quick-action"} href={action.href} key={action.id}>
                  <span>{action.done ? "Op orde" : "Actie"}</span>
                  <strong>{action.title}</strong>
                  <small>{action.detail}</small>
                </Link>
              ))}
            </div>
          </section>
          {error && <div className="error">{error}</div>}
          <ModuleSubmenu title="Snelle invoer" detail="Taak, boodschap, afspraak of notitie vastleggen">
            <QuickAddForm />
          </ModuleSubmenu>
          {!demo && <QuickPresetGrid />}
        </div>
        <aside className="card">
          <div className="section-head">
            <div>
              <h2>Waar komt het terecht?</h2>
              <p className="muted">Kies het type en de app zet het item in de juiste lijst.</p>
            </div>
            <span className="summary-icon">
              <Zap size={18} />
            </span>
          </div>
          <ul className="list">
            <li className="list-row">
              <CheckSquare size={18} />
              <div className="row-main">
                <div className="row-title">Taak</div>
                <div className="row-meta">Komt in Taken met prioriteit en deadline.</div>
              </div>
            </li>
            <li className="list-row">
              <ShoppingBasket size={18} />
              <div className="row-main">
                <div className="row-title">Boodschap</div>
                <div className="row-meta">Komt op de gedeelde boodschappenlijst.</div>
              </div>
            </li>
            <li className="list-row">
              <MessageSquare size={18} />
              <div className="row-main">
                <div className="row-title">Prikbordbericht</div>
                <div className="row-meta">Komt op het gezinsprikbord.</div>
              </div>
            </li>
            <li className="list-row">
              <CalendarDays size={18} />
              <div className="row-main">
                <div className="row-title">Afspraak</div>
                <div className="row-meta">Komt in de gezinsagenda; details worden locatie.</div>
              </div>
            </li>
            <li className="list-row">
              <Utensils size={18} />
              <div className="row-main">
                <div className="row-title">Maaltijd</div>
                <div className="row-meta">Komt in Maaltijden; details worden ingredienten.</div>
              </div>
            </li>
            <li className="list-row">
              <Landmark size={18} />
              <div className="row-main">
                <div className="row-title">Betaalmoment</div>
                <div className="row-meta">Komt in Geld; zet bedrag in titel of details, bijvoorbeeld schoolfoto 12,50.</div>
              </div>
            </li>
          </ul>
          <div className="quick-actions" style={{ marginTop: 16 }}>
            <Link className="button" href="/taken">Taken</Link>
            <Link className="button" href="/boodschappen">Boodschappen</Link>
            <Link className="button" href="/prikbord">Prikbord</Link>
            <Link className="button" href="/agenda">Agenda</Link>
            <Link className="button" href="/boodschappen?tab=maaltijden">Maaltijden</Link>
            <Link className="button" href="/geld">Geld</Link>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}

function QuickMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="quick-metric">
      <span className="quick-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
