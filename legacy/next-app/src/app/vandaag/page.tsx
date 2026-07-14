import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ArrowRight,
  Banknote,
  CalendarDays,
  Check,
  CheckSquare,
  Gauge,
  MessageSquare,
  ShoppingBasket,
  Sun,
  Utensils,
  Wrench,
} from "lucide-react";
import { completeMaintenanceItem, toggleShoppingItem, toggleTask } from "@/app/actions";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { QuickAddForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { memberName, shortDate } from "@/lib/format";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { getAppData, getUser } from "@/lib/local-data";
import { buildTodayInsight, type TodayAction } from "@/lib/today-insights";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const now = new Date().toISOString();
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <TodayContent data={await getLocalAppData()} now={now} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <TodayContent data={data} now={now} />;
}

function TodayContent({ data, now }: { data: AppData; now: string }) {
  const insight = buildTodayInsight(data, now);

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Dagplanning</span>
          <h1>Vandaag</h1>
          <p className="hero-copy">
            Alles wat het gezin vandaag nodig heeft: deadlines, afspraken, eten, boodschappen en huiszaken.
          </p>
          <div className="quick-actions">
            <Link className="button primary" href="/snel">Snel toevoegen</Link>
            <Link className="button" href="/agenda">Agenda</Link>
            <Link className="button" href="/taken?filter=vandaag">Taken vandaag</Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Status</span>
            <h2 style={{ margin: "8px 0 0" }}>{insight.openTasks.length === 0 ? "Rustige dag" : `${insight.openTasks.length} actie${insight.openTasks.length === 1 ? "" : "s"} nodig`}</h2>
            <p className="muted">Gebaseerd op open items tot en met vandaag.</p>
          </div>
          <div className="today-stack">
            <TodayMetric label="Afspraken" value={insight.todaysEvents.length} />
            <TodayMetric label="Boodschappen" value={insight.shopping.length} />
            <TodayMetric label="Onderhoud" value={insight.maintenance.length} />
          </div>
        </aside>
      </section>

      <section className="card today-control">
        <div className="section-head">
          <div>
            <span className="eyebrow">Dagregie</span>
            <h2>{insight.dayLabel}</h2>
            <p className="muted">{insight.focusAction.reason}</p>
          </div>
          <div className="today-control-actions">
            <Link className="button primary" href={insight.focusAction.href}>
              {insight.focusAction.label} <ArrowRight size={16} />
            </Link>
            <Link className="button" href="/week">Week</Link>
          </div>
        </div>
        <div className="today-pressure-row">
          <div className="today-pressure-card">
            <span className="today-pressure-icon"><Gauge size={18} /></span>
            <div>
              <span>Dagdruk</span>
              <strong>{insight.dayPressure}%</strong>
            </div>
            <div className="progress-bar" aria-hidden="true">
              <span style={{ width: `${insight.dayPressure}%` }} />
            </div>
          </div>
          <div className="today-control-grid">
            <TodayControlMetric icon={<CheckSquare size={17} />} label="Actie" value={insight.openTasks.length} detail={`${insight.overdueTasks.length} te laat, ${insight.dueTodayTasks.length} vandaag`} href="/taken?filter=vandaag" />
            <TodayControlMetric icon={<CalendarDays size={17} />} label="Planning" value={insight.todaysEvents.length} detail={`${insight.tomorrowEvents.length} morgen`} href="/agenda" />
            <TodayControlMetric icon={<Utensils size={17} />} label="Eten" value={insight.meals.length} detail={insight.meals.length === 0 ? "Nog plannen" : "Staat klaar"} href="/boodschappen?tab=maaltijden" />
            <TodayControlMetric icon={<ShoppingBasket size={17} />} label="Boodschappen" value={insight.openShopping.length} detail={insight.openShopping.length === 0 ? "Lijst leeg" : "Nog open"} href="/boodschappen" />
            <TodayControlMetric icon={<Wrench size={17} />} label="Huis" value={insight.maintenanceAll.length} detail="Binnen 7 dagen" href="/onderhoud" />
            <TodayControlMetric icon={<Banknote size={17} />} label="Geld" value={insight.financeDue.length} detail="Betaalmomenten" href="/geld" />
          </div>
        </div>
        <div className="today-readiness">
          <div>
            <span className="eyebrow">Dagcheck</span>
            <strong>{insight.readinessScore}%</strong>
            <small>{insight.completedActions} van {insight.actions.length} punten op orde</small>
          </div>
          <div className="progress-bar" aria-hidden="true">
            <span style={{ width: `${insight.readinessScore}%` }} />
          </div>
        </div>
        <div className="today-action-grid">
          {insight.actions.map((action) => (
            <TodayActionCard key={action.id} action={action} />
          ))}
        </div>
      </section>

      <section className="grid two-col section-stack">
        <div className="grid">
          <TodayCard icon={<CheckSquare size={18} />} title="Taken die nu aandacht vragen" href="/taken?filter=vandaag" count={insight.openTasks.length}>
            <ul className="list">
              {insight.openTasks.length === 0 && <li className="empty-state">Geen open taken met deadline vandaag of eerder.</li>}
              {insight.openTasks.slice(0, 8).map((task) => (
                <li className="list-row" key={task.id}>
                  <div className="row-main">
                    <div className="row-title">{task.title}</div>
                    <div className="row-meta">
                      {memberName(task.assignee_id, data.members)} · {task.priority} · {shortDate(task.due_date)}
                    </div>
                    {task.description && <div className="row-description">{task.description}</div>}
                  </div>
                  <form action={toggleTask}>
                    <input type="hidden" name="id" value={task.id} />
                    <input type="hidden" name="status" value={task.status} />
                    <button className="icon-button" title="Afronden" aria-label="Afronden">
                      <Check size={17} />
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </TodayCard>

          <TodayCard icon={<CalendarDays size={18} />} title="Afspraken vandaag" href="/agenda" count={insight.todaysEvents.length}>
            <ul className="list">
              {insight.todaysEvents.length === 0 && <li className="empty-state">Geen afspraken vandaag.</li>}
              {insight.todaysEvents.map((event) => (
                <li className="list-row" key={event.id}>
                  <div className="row-main">
                    <div className="row-title">{event.title}</div>
                    <div className="row-meta">
                      {shortDate(event.starts_at)}{event.location ? ` · ${event.location}` : ""}
                    </div>
                    {event.external_calendar_name && <div className="row-description">{event.external_calendar_name}</div>}
                  </div>
                  {event.source_provider && <span className="status">Outlook</span>}
                </li>
              ))}
            </ul>
          </TodayCard>

          <TodayCard icon={<Utensils size={18} />} title="Eten vandaag" href="/boodschappen?tab=maaltijden" count={insight.meals.length}>
            <ul className="list">
              {insight.meals.length === 0 && <li className="empty-state">Nog geen maaltijd gepland voor vandaag.</li>}
              {insight.meals.map((meal) => (
                <li className="list-row" key={meal.id}>
                  <div className="row-main">
                    <div className="row-title">{meal.title}</div>
                    <div className="row-meta">{mealTypeLabel(meal.meal_type)}</div>
                    {meal.ingredients && <div className="row-description">{meal.ingredients}</div>}
                  </div>
                </li>
              ))}
            </ul>
          </TodayCard>
        </div>

        <div className="grid">
          <TodayCard icon={<ShoppingBasket size={18} />} title="Boodschappen open" href="/boodschappen" count={insight.shopping.length}>
            <ul className="list">
              {insight.shopping.length === 0 && <li className="empty-state">Geen open boodschappen.</li>}
              {insight.shopping.map((item) => (
                <li className="list-row" key={item.id}>
                  <div className="row-main">
                    <div className="row-title">{item.name}</div>
                    <div className="row-meta">{[item.quantity, item.category].filter(Boolean).join(" · ") || "Geen details"}</div>
                  </div>
                  <form action={toggleShoppingItem}>
                    <input type="hidden" name="id" value={item.id} />
                    <input type="hidden" name="checked" value={String(item.checked)} />
                    <button className="icon-button" title="Afvinken" aria-label="Afvinken">
                      <Check size={17} />
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </TodayCard>

          <TodayCard icon={<Wrench size={18} />} title="Huiszaken deze week" href="/onderhoud" count={insight.maintenance.length}>
            <ul className="list">
              {insight.maintenance.length === 0 && <li className="empty-state">Geen onderhoud dat deze week aandacht vraagt.</li>}
              {insight.maintenance.map((item) => (
                <li className="list-row" key={item.id}>
                  <div className="row-main">
                    <div className="row-title">{item.title}</div>
                    <div className="row-meta">{[item.area, item.provider, shortDate(item.due_date)].filter(Boolean).join(" · ")}</div>
                    {item.notes && <div className="row-description">{item.notes}</div>}
                  </div>
                  <form action={completeMaintenanceItem}>
                    <input type="hidden" name="id" value={item.id} />
                    <button className="icon-button" title="Afronden" aria-label="Afronden">
                      <Check size={17} />
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </TodayCard>

          <TodayCard icon={<MessageSquare size={18} />} title="Vastgezette berichten" href="/prikbord" count={insight.pinnedNotes.length}>
            <ul className="list">
              {insight.pinnedNotes.length === 0 && <li className="empty-state">Geen vastgezette berichten.</li>}
              {insight.pinnedNotes.map((note) => (
                <li className="list-row" key={note.id}>
                  <div className="row-main">
                    <div className="row-title">{note.title}</div>
                    <div className="row-meta">{note.category} · {shortDate(note.created_at)}</div>
                    <div className="row-description">{note.body}</div>
                  </div>
                </li>
              ))}
            </ul>
          </TodayCard>

          <TodayCard icon={<Sun size={18} />} title="Morgen alvast" href="/agenda" count={insight.tomorrowEvents.length}>
            <ul className="list">
              {insight.tomorrowEvents.length === 0 && <li className="empty-state">Geen afspraken voor morgen gevonden.</li>}
              {insight.tomorrowEvents.map((event) => (
                <li className="list-row" key={event.id}>
                  <div className="row-main">
                    <div className="row-title">{event.title}</div>
                    <div className="row-meta">{shortDate(event.starts_at)}</div>
                  </div>
                </li>
              ))}
            </ul>
          </TodayCard>
        </div>
      </section>

      <section style={{ marginTop: 22 }}>
        <ModuleSubmenu title="Snelle invoer" detail="Leg direct iets vast vanuit vandaag">
          <QuickAddForm />
        </ModuleSubmenu>
      </section>
    </AppShell>
  );
}

function TodayCard({ icon, title, href, count, children }: { icon: React.ReactNode; title: string; href: string; count: number; children: React.ReactNode }) {
  return (
    <div className="card module-card">
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          <p className="muted">Direct vanuit het dagoverzicht.</p>
        </div>
        <Link className="status" href={href}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{icon}{count}</span>
        </Link>
      </div>
      {children}
    </div>
  );
}

function TodayMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="today-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TodayControlMetric({
  icon,
  label,
  value,
  detail,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  detail: string;
  href: string;
}) {
  return (
    <Link className="today-control-metric" href={href}>
      <span className="today-control-icon">{icon}</span>
      <span>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </span>
    </Link>
  );
}

function TodayActionCard({ action }: { action: TodayAction }) {
  return (
    <Link className={`today-action-card ${action.done ? "done" : action.tone}`} href={action.href}>
      <span className="today-action-mark">{action.done ? <Check size={16} /> : <ArrowRight size={16} />}</span>
      <span>
        <strong>{action.label}</strong>
        <small>{action.detail}</small>
      </span>
    </Link>
  );
}

function mealTypeLabel(mealType: string) {
  if (mealType === "ontbijt") return "Ontbijt";
  if (mealType === "lunch") return "Lunch";
  if (mealType === "snack") return "Snack";
  return "Avondeten";
}
