import Link from "next/link";
import { redirect } from "next/navigation";
import { CalendarDays, CheckSquare, Euro, Gauge, ShoppingBasket, Utensils, Wrench } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { dateKey, dateSortValue } from "@/lib/date-keys";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { memberName, money, shortDate } from "@/lib/format";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { buildWeekInsight } from "@/lib/week-insights";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function WeekPage() {
  const now = new Date().toISOString();
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <WeekContent data={await getLocalAppData()} now={now} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <WeekContent data={data} now={now} />;
}

function WeekContent({ data, now }: { data: AppData; now: string }) {
  const insight = buildWeekInsight(data, now);
  const { today, days, weekEvents, weekTasks, weekMeals, weekFinance, weekMaintenance, openShopping } = insight;

  return (
    <AppShell>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Gezinsplanning</span>
          <h1>Week</h1>
          <p className="hero-copy">
            De gezinsweek vanaf {data.householdPreferences.week_starts_on === "sunday" ? "zondag" : "maandag"} in een oogopslag: afspraken, taken en maaltijden per dag.
          </p>
          <div className="quick-actions">
            <Link className="button primary" href="/agenda">Afspraak toevoegen</Link>
            <Link className="button" href="/taken">Taken plannen</Link>
            <Link className="button" href="/boodschappen?tab=maaltijden">Maaltijd plannen</Link>
            <Link className="button" href="/boodschappen">Boodschappenlijst</Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Deze week</span>
            <h2 style={{ margin: "8px 0 0" }}>{insight.plannedItemCount} geplande items</h2>
            <p className="muted">Vanaf vandaag tot en met {shortDate(insight.weekEnd)}.</p>
          </div>
          <div className="today-stack">
            <Metric label="Afspraken" value={weekEvents.length} />
            <Metric label="Taken" value={weekTasks.length} />
            <Metric label="Betaalmomenten" value={weekFinance.length} />
            <Metric label="Boodschappen" value={openShopping} />
          </div>
        </aside>
      </section>

      <section className="week-control card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Weekregie</span>
            <h2>Waar moet het gezin op letten?</h2>
            <p className="muted">{insight.score}/{insight.totalChecks} onderdelen op orde voor deze week.</p>
          </div>
          <span className="summary-icon"><Gauge size={18} /></span>
        </div>
        <div className="week-control-grid">
          <WeekMetric label="Drukste dag" value={insight.busiestDay && insight.busiestDay.load > 0 ? insight.busiestDay.dayName : "Rustig"} detail={insight.busiestDay && insight.busiestDay.load > 0 ? `${insight.busiestDay.load} items op ${insight.busiestDay.label}` : "Geen piekdag gevonden"} />
          <WeekMetric label="Geld deze week" value={money(insight.financeTotal)} detail={`${weekFinance.length} open betaalmoment${weekFinance.length === 1 ? "" : "en"}`} />
          <WeekMetric label="Huiszaken" value={weekMaintenance.length} detail="Onderhoud met deadline deze week" />
          <WeekMetric label="Maaltijden gepland" value={weekMeals.length} detail="Geplande eetmomenten" />
        </div>
        <div className="week-readiness">
          <div>
            <strong>Weekscore</strong>
            <span>{insight.percent}% ingericht</span>
          </div>
          <div className="setup-bar" aria-hidden="true">
            <span style={{ width: `${insight.percent}%` }} />
          </div>
        </div>
        <div className="week-action-grid">
          {insight.actions.map((action) => (
            <Link className={action.done ? "week-action done" : "week-action"} href={action.href} key={action.id}>
              <span>{action.done ? "Op orde" : "Actie"}</span>
              <strong>{action.title}</strong>
              <small>{action.detail}</small>
            </Link>
          ))}
        </div>
      </section>

      <section className="week-board section-stack">
        {days.map((day) => {
          const events = weekEvents.filter((event) => dateKey(event.starts_at) === day.date).sort((a, b) => dateSortValue(a.starts_at) - dateSortValue(b.starts_at));
          const tasks = weekTasks.filter((task) => dateKey(task.due_date) === day.date);
          const meals = weekMeals.filter((meal) => dateKey(meal.planned_date as string | Date) === day.date);
          const finance = weekFinance.filter((item) => dateKey(item.due_date) === day.date);
          const maintenance = weekMaintenance.filter((item) => dateKey(item.due_date) === day.date);
          const load = events.length + tasks.length + meals.length + finance.length + maintenance.length;
          return (
            <article className="card week-day" key={day.date}>
              <header>
                <div>
                  <span className={day.date === today ? "status accent" : "status"}>{day.date === today ? "Vandaag" : day.dayName}</span>
                  <h2>{day.label}</h2>
                </div>
                <span className={day.load >= 5 ? "week-load busy" : "week-load"}>{load}</span>
              </header>
              <WeekSection icon={<CalendarDays size={15} />} title="Agenda" href="/agenda" count={events.length}>
                {events.length === 0 && <li className="week-empty">Geen afspraken</li>}
                {events.slice(0, 4).map((event) => (
                  <li key={event.id}>
                    <strong>{event.title}</strong>
                    <span>{shortDate(event.starts_at)}{event.location ? ` · ${event.location}` : ""}</span>
                  </li>
                ))}
              </WeekSection>
              <WeekSection icon={<CheckSquare size={15} />} title="Taken" href="/taken?filter=open" count={tasks.length}>
                {tasks.length === 0 && <li className="week-empty">Geen taken</li>}
                {tasks.slice(0, 4).map((task) => (
                  <li key={task.id}>
                    <strong>{task.title}</strong>
                    <span>{memberName(task.assignee_id, data.members)} · {task.priority}</span>
                  </li>
                ))}
              </WeekSection>
              <WeekSection icon={<Euro size={15} />} title="Geld" href="/geld" count={finance.length}>
                {finance.length === 0 && <li className="week-empty">Geen betaalmomenten</li>}
                {finance.slice(0, 3).map((item) => (
                  <li key={item.id}>
                    <strong>{item.title}</strong>
                    <span>{item.category} · {money(item.amount_cents)}</span>
                  </li>
                ))}
              </WeekSection>
              <WeekSection icon={<Wrench size={15} />} title="Huis" href="/onderhoud" count={maintenance.length}>
                {maintenance.length === 0 && <li className="week-empty">Geen huiszaken</li>}
                {maintenance.slice(0, 3).map((item) => (
                  <li key={item.id}>
                    <strong>{item.title}</strong>
                    <span>{[item.area, item.provider].filter(Boolean).join(" · ") || "Onderhoud"}</span>
                  </li>
                ))}
              </WeekSection>
              <WeekSection icon={<Utensils size={15} />} title="Eten" href="/boodschappen?tab=maaltijden" count={meals.length}>
                {meals.length === 0 && <li className="week-empty">Nog niet gepland</li>}
                {meals.slice(0, 3).map((meal) => (
                  <li key={meal.id}>
                    <strong>{meal.title}</strong>
                    <span>{mealTypeLabel(meal.meal_type)}</span>
                  </li>
                ))}
              </WeekSection>
            </article>
          );
        })}
      </section>

      <section className="card week-shopping">
        <div className="section-head">
          <div>
            <h2>Boodschappen voor de week</h2>
            <p className="muted">{openShopping} open items op de gedeelde lijst.</p>
          </div>
          <Link className="status" href="/boodschappen">
            <ShoppingBasket size={15} /> Open lijst
          </Link>
        </div>
        <div className="tag-list">
          {data.shoppingItems.filter((item) => !item.checked).slice(0, 12).map((item) => (
            <span className="tag" key={item.id}>{item.name}</span>
          ))}
          {openShopping === 0 && <span className="muted">Geen open boodschappen.</span>}
        </div>
      </section>
    </AppShell>
  );
}

function WeekMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="week-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function WeekSection({ icon, title, href, count, children }: { icon: React.ReactNode; title: string; href: string; count: number; children: React.ReactNode }) {
  return (
    <section className="week-section">
      <Link href={href}>
        <span>{icon}{title}</span>
        <small>{count}</small>
      </Link>
      <ul>{children}</ul>
    </section>
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

function mealTypeLabel(mealType: string) {
  if (mealType === "ontbijt") return "Ontbijt";
  if (mealType === "lunch") return "Lunch";
  if (mealType === "snack") return "Snack";
  return "Avondeten";
}
