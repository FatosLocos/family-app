import Link from "next/link";
import { redirect } from "next/navigation";
import { Activity, AlertTriangle, Bell, CalendarRange, CalendarDays, CheckSquare, ClipboardCheck, Database, FileText, Gift, Home, MessageSquare, PlugZap, Repeat, Search, ShoppingBasket, Sun, UsersRound, Utensils, Wrench, Zap } from "lucide-react";
import { Landing } from "@/components/auth-gate";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { FamilyCommandCenter } from "@/components/family-command-center";
import { GettingStartedPanel } from "@/components/getting-started-panel";
import { Onboarding } from "@/components/onboarding";
import { CalendarList, FinanceList, HouseholdDocumentList, HouseholdNoteList, MaintenanceList, MealPlanList, ShoppingListView, TaskList, WishlistItemList } from "@/components/module-lists";
import { getAppData, getUser } from "@/lib/local-data";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { demoData } from "@/lib/demo-data";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { dateKey } from "@/lib/date-keys";
import { money } from "@/lib/format";
import { buildFamilyInsights, type FamilyInsight } from "@/lib/insights";
import { buildNotifications } from "@/lib/notifications";
import { buildSetupSteps, setupProgress } from "@/lib/setup";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const now = new Date().toISOString();
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <Dashboard data={await getLocalAppData()} now={now} localMode />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) return <Landing />;

  const data = await getAppData(user.id);
  if (!data) return <Onboarding />;

  return <Dashboard data={data} now={now} />;
}

function Dashboard({ data, now, demo = false, localMode = false }: { data: typeof demoData; now: string; demo?: boolean; localMode?: boolean }) {
  const openTasks = data.tasks.filter((task) => task.status === "open").length;
  const today = now.slice(0, 10);
  const dueToday = data.tasks.filter((task) => task.status === "open" && dateKey(task.due_date) === today).length;
  const shoppingOpen = data.shoppingItems.filter((item) => !item.checked).length;
  const monthlyTotal = data.financeItems
    .filter((item) => item.frequency === "maandelijks" && item.status !== "betaald")
    .reduce((sum, item) => sum + item.amount_cents, 0);
  const nowTime = new Date(now).getTime();
  const upcomingEvents = data.calendarEvents.filter((event) => new Date(event.starts_at).getTime() >= nowTime).length;
  const upcomingMeals = data.mealPlans.filter((meal) => dateKey(meal.planned_date as string | Date)! >= today).length;
  const openMaintenance = data.maintenanceItems.filter((item) => item.status === "open").length;
  const pinnedNotes = data.householdNotes.filter((note) => note.pinned).length;
  const openWishes = data.wishlistItems.filter((item) => item.status === "open").length;
  const expiringDocuments = data.householdDocuments.filter((document) => dateKey(document.expires_at) !== null && dateKey(document.expires_at)! >= today).length;
  const insights = buildFamilyInsights(data, now);
  const notifications = buildNotifications(data, now);
  const urgentNotifications = notifications.filter((item) => item.tone === "urgent").length;
  const setup = setupProgress(buildSetupSteps(data));
  const preferredStart = dashboardPreference(data.householdPreferences.default_dashboard);

  return (
    <AppShell demo={demo}>
      <section className="dashboard-hero">
        <div className="hero-panel">
          <span className="eyebrow">Gezinsdashboard</span>
          <h1>{data.household.name}</h1>
          <p className="hero-copy">
            {demo
              ? "Demo-modus: bekijk de suite zonder PostgreSQL-configuratie."
              : "Een compact overzicht voor vandaag: wat moet gebeuren, wat moet mee, wat komt eraan en welke vaste lasten staan klaar."}
          </p>
          <div className="quick-actions">
            <Link className="button primary" href={preferredStart.href}>
              {preferredStart.icon} {preferredStart.label}
            </Link>
            <Link className="button primary" href="/week">
              <CalendarRange size={17} /> Week
            </Link>
            <Link className="button primary" href="/activiteit">
              <Activity size={17} /> Activiteit
            </Link>
            <Link className="button primary" href="/meldingen">
              <Bell size={17} /> Meldingen
            </Link>
            <Link className="button primary" href="/snel">
              <Zap size={17} /> Snel toevoegen
            </Link>
            <Link className="button primary" href="/zoeken">
              <Search size={17} /> Zoeken
            </Link>
            <Link className="button" href="/noodkaart">
              <AlertTriangle size={17} /> Noodkaart
            </Link>
          </div>
        </div>
        <aside className="today-panel">
          <div>
            <span className="eyebrow">Vandaag</span>
            <h2 style={{ margin: "8px 0 0" }}>{dueToday === 0 ? "Geen deadlines vandaag" : `${dueToday} taak${dueToday === 1 ? "" : "en"} vandaag`}</h2>
            <p className="muted">Openstaande signalen voor het huishouden.</p>
          </div>
          <div className="today-stack">
            <div className="today-row">
              <span>Boodschappen open</span>
              <strong>{shoppingOpen}</strong>
            </div>
            <div className="today-row">
              <span>Afspraken gepland</span>
              <strong>{upcomingEvents}</strong>
            </div>
            <div className="today-row">
              <span>Gezinsleden</span>
              <strong>{data.members.length}</strong>
            </div>
          </div>
        </aside>
      </section>
      <FamilyCommandCenter data={data} now={now} />
      {!demo && <GettingStartedPanel data={data} localMode={localMode} />}
      <section className="grid dashboard-grid section-stack">
        <SummaryCard icon={<CheckSquare size={20} />} title="Open taken" value={String(openTasks)} href="/taken" />
        <SummaryCard icon={<Bell size={20} />} title="Meldingen" value={String(urgentNotifications || notifications.length)} href="/meldingen" />
        <SummaryCard icon={<Activity size={20} />} title="Activiteit" value={String(notifications.length + upcomingEvents)} href="/activiteit" />
        <SummaryCard icon={<ClipboardCheck size={20} />} title="Inrichting" value={`${setup.percent}%`} href="/inrichting" />
        <SummaryCard icon={<ShoppingBasket size={20} />} title="Boodschappen" value={String(shoppingOpen)} href="/boodschappen" />
        <SummaryCard icon={<Utensils size={20} />} title="Maaltijden" value={String(upcomingMeals)} href="/boodschappen?tab=maaltijden" />
        <SummaryCard icon={<MessageSquare size={20} />} title="Prikbord" value={String(pinnedNotes)} href="/prikbord" />
        <SummaryCard icon={<Gift size={20} />} title="Wishlist" value={String(openWishes)} href="/wishlist" />
        <SummaryCard icon={<FileText size={20} />} title="Documenten" value={String(expiringDocuments)} href="/documenten" />
      </section>
      <section className="section-stack">
        <div className="section-head section-head-spaced">
          <div>
            <h2 style={{ margin: 0 }}>Modules</h2>
            <p className="muted" style={{ margin: "6px 0 0" }}>Snel naar de onderdelen van de gezinsapp.</p>
          </div>
        </div>
        <div className="grid module-launcher">
          <ModuleTile icon={<Sun size={18} />} title="Vandaag" description="Een dagbeeld met taken, afspraken, eten en boodschappen." href="/vandaag" />
          <ModuleTile icon={<CalendarRange size={18} />} title="Week" description="Planning voor de komende zeven dagen." href="/week" />
          <ModuleTile icon={<Activity size={18} />} title="Activiteit" description="Tijdlijn van recente en aankomende gezinsgebeurtenissen." href="/activiteit" />
          <ModuleTile icon={<Bell size={18} />} title="Meldingen" description="Centrale inbox voor reminders uit alle modules." href="/meldingen" />
          <ModuleTile icon={<ClipboardCheck size={18} />} title="Inrichting" description="Checklist om de app compleet te maken." href="/inrichting" />
          <ModuleTile icon={<Database size={18} />} title="Data & backup" description="Bekijk opslag en download een gezinsdata-export." href="/data" />
          <ModuleTile icon={<AlertTriangle size={18} />} title="Noodkaart" description="Belangrijke contacten, huisinfo en documenten." href="/noodkaart" />
          <ModuleTile icon={<Zap size={18} />} title="Snel toevoegen" description="Een taak, boodschap of prikbordbericht direct vastleggen." href="/snel" />
          <ModuleTile icon={<MessageSquare size={18} />} title="Prikbord" description="Korte mededelingen en vastgezette berichten." href="/prikbord" />
          <ModuleTile icon={<Search size={18} />} title="Zoeken" description="Vind alles terug over alle modules heen." href="/zoeken" />
          <ModuleTile icon={<CheckSquare size={18} />} title="Taken" description="Taken, subtaken, deadlines en herhaling." href="/taken" />
          <ModuleTile icon={<ShoppingBasket size={18} />} title="Boodschappen" description="Slimme lijst, prijzen en OCR-bonnen." href="/boodschappen" />
          <ModuleTile icon={<Gift size={18} />} title="Wishlist" description="Deelbare verlanglijst met reserveren en afstrepen." href="/wishlist" />
          <ModuleTile icon={<Utensils size={18} />} title="Maaltijden" description="Weekplanning met ingrediënten naar boodschappen." href="/boodschappen?tab=maaltijden" />
          <ModuleTile icon={<Repeat size={18} />} title="Routines" description="Alle terugkerende taken, boodschappen en onderhoud." href="/routines" />
          <ModuleTile icon={<UsersRound size={18} />} title="Wie doet wat" description="Werkverdeling per gezinslid." href="/wie-doet-wat" />
          <ModuleTile icon={<CalendarDays size={18} />} title="Agenda" description="Gezinsagenda en Outlook-koppelingen." href="/agenda" />
          <ModuleTile icon={<FileText size={18} />} title="Documenten" description="Bewaarplek, referenties en vervaldatums." href="/documenten" />
          <ModuleTile icon={<Wrench size={18} />} title="Onderhoud" description="Huisonderhoud met terugkerende planning." href="/onderhoud" />
          <ModuleTile icon={<Home size={18} />} title="Smart home" description="Hue, Home Assistant en Google Home." href="/home" />
          <ModuleTile icon={<PlugZap size={18} />} title="Koppelingen" description="Status van agenda, bank, taken en smart home." href="/koppelingen" />
        </div>
      </section>
      <section className="grid two-col section-stack">
        <div className="grid">
          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Signalen</h2>
                <p className="muted">Wat nu aandacht verdient.</p>
              </div>
              <span className="status">{insights.length}</span>
            </div>
            <InsightList insights={insights} />
          </div>
          <HouseholdNoteList data={data} limit={3} readOnly={demo} />
          <WishlistItemList data={data} limit={3} readOnly={demo} />
          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Taken</h2>
                <p className="muted">Open acties voor thuis.</p>
              </div>
              <Link className="status" href="/taken">
                Openen
              </Link>
            </div>
            <TaskList data={data} limit={4} readOnly={demo} />
          </div>
          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Boodschappen</h2>
                <p className="muted">Lijst, herhaling en prijzen.</p>
              </div>
              <Link className="status" href="/boodschappen">
                Lijst
              </Link>
            </div>
            <ShoppingListView data={data} limit={4} readOnly={demo} />
          </div>
          <MealPlanList data={data} limit={3} readOnly={demo} />
        </div>
        <div className="grid">
          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Geld</h2>
                <p className="muted">Vaste lasten en budgetposten.</p>
              </div>
              <Link className="status accent" href="/geld">
                {money(monthlyTotal)}
              </Link>
            </div>
            <FinanceList data={data} limit={4} readOnly={demo} />
          </div>
          <div className="card module-card">
            <div className="section-head">
              <div>
                <h2>Agenda</h2>
                <p className="muted">Gezinsplanning en Outlook.</p>
              </div>
              <Link className="status" href="/agenda">
                Planning
              </Link>
            </div>
            <CalendarList data={data} limit={4} readOnly={demo} />
          </div>
          <MaintenanceList data={data} limit={4} readOnly={demo} />
          <HouseholdDocumentList data={data} limit={3} readOnly={demo} />
          <SummaryCard icon={<Wrench size={20} />} title="Onderhoud" value={String(openMaintenance)} href="/onderhoud" />
          <Link className="button" href="/home">
            <Home size={17} /> Home Assistant openen
          </Link>
          <Link className="button" href="/koppelingen">
            <PlugZap size={17} /> Koppelingen
          </Link>
        </div>
      </section>
    </AppShell>
  );
}

function dashboardPreference(value: string) {
  if (value === "compact") return { href: "/", label: "Dashboard", icon: <Home size={17} /> };
  if (value === "uitgebreid") return { href: "/activiteit", label: "Activiteit", icon: <Activity size={17} /> };
  return { href: "/vandaag", label: "Vandaag", icon: <Sun size={17} /> };
}

function InsightList({ insights }: { insights: FamilyInsight[] }) {
  return (
    <ul className="insight-list">
      {insights.length === 0 && <li className="empty-state">Geen signalen. Alles is rustig.</li>}
      {insights.map((insight) => (
        <li className={`insight-row ${insight.tone}`} key={insight.id}>
          <Link href={insight.href}>
            <span className="insight-dot" />
            <span>
              <strong>{insight.title}</strong>
              <small>{insight.detail}</small>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function SummaryCard({ icon, title, value, href }: { icon: React.ReactNode; title: string; value: string; href: string }) {
  return (
    <Link href={href} className="card interactive summary-card">
      <div className="summary-head">
        <h2>{title}</h2>
        <span className="summary-icon">{icon}</span>
      </div>
      <div className="metric">{value}</div>
    </Link>
  );
}

function ModuleTile({ icon, title, description, href }: { icon: React.ReactNode; title: string; description: string; href: string }) {
  return (
    <Link href={href} className="card interactive module-tile">
      <span className="summary-icon">{icon}</span>
      <strong>{title}</strong>
      <p>{description}</p>
    </Link>
  );
}
