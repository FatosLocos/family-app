import { redirect } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { DemoWorkspace } from "@/components/demo-workspace";
import { MaintenanceForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { MaintenanceList } from "@/components/module-lists";
import { demoData } from "@/lib/demo-data";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { getAppData, getUser } from "@/lib/local-data";
import { dateKey } from "@/lib/date-keys";
import { shortDate } from "@/lib/format";
import { buildMaintenanceReadiness } from "@/lib/maintenance-readiness";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function MaintenancePage() {
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <MaintenanceContent data={await getLocalAppData()} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <MaintenanceContent data={data} />;
}

function MaintenanceContent({ data, demo = false }: { data: typeof demoData; demo?: boolean }) {
  const today = dateKey(new Date()) ?? new Date().toISOString().slice(0, 10);
  const overdue = data.maintenanceItems.filter((item) => {
    const dueDate = dateKey(item.due_date);
    return item.status === "open" && dueDate && dueDate < today;
  }).length;
  const open = data.maintenanceItems.filter((item) => item.status === "open").length;

  return (
    <AppShell demo={demo}>
      <section className="grid two-col">
        <div className="grid">
          <div className="page-heading">
            <h1>Onderhoud</h1>
            <p className="muted">
              {open} open items · {overdue} te laat
            </p>
          </div>
          <MaintenanceControlPanel data={data} today={today} />
          <MaintenanceList data={data} readOnly={demo} />
        </div>
        <div className="grid">
          {demo ? (
            <DemoPanel />
          ) : (
            <ModuleSubmenu title="Onderhoud toevoegen" detail="Controle, klus of terugkerend onderhoud plannen">
              <MaintenanceForm />
            </ModuleSubmenu>
          )}
        </div>
      </section>
    </AppShell>
  );
}

function MaintenanceControlPanel({ data, today }: { data: AppData; today: string }) {
  const readiness = buildMaintenanceReadiness(data, today);

  return (
    <div className="maintenance-control card">
      <div className="section-head">
        <div>
          <h2>Onderhoudsstatus</h2>
          <p className="muted">Planning, achterstand en vaste controles.</p>
        </div>
        <span className={readiness.overdue.length > 0 ? "status accent" : "status"}>{readiness.overdue.length} te laat</span>
      </div>
      <div className="maintenance-control-grid">
        <MaintenanceMetric label="Open" value={readiness.open.length} />
        <MaintenanceMetric label="Deze week" value={readiness.thisWeek.length} />
        <MaintenanceMetric label="Deze maand" value={readiness.thisMonth.length} />
        <MaintenanceMetric label="Terugkerend" value={readiness.recurring.length} />
      </div>
      <div className="maintenance-readiness">
        <div>
          <strong>Onderhoud op orde</strong>
          <span>{readiness.score}/{readiness.totalChecks} punten op orde</span>
        </div>
        <div className="setup-bar" aria-hidden="true">
          <span style={{ width: `${readiness.percent}%` }} />
        </div>
      </div>
      <div className="maintenance-next-row">
        <div>
          <strong>Volgende onderhoudstaak</strong>
          <p className="muted">
            {readiness.nextItem ? `${readiness.nextItem.title} · ${shortDate(readiness.nextItem.due_date)}${readiness.nextItem.provider ? ` · ${readiness.nextItem.provider}` : ""}` : "Geen geplande onderhoudstaken."}
          </p>
        </div>
        <div className="maintenance-areas">
          {readiness.areaSummaries.length === 0 ? (
            <span className="status">Geen onderdelen</span>
          ) : (
            readiness.areaSummaries.map(({ area, count, open }) => (
              <span className="status" key={area}>
                {area}: {open}/{count} open
              </span>
            ))
          )}
        </div>
      </div>
      <div className="maintenance-action-grid">
        {readiness.actions.map((action) => (
          <Link className={action.done ? "maintenance-action done" : "maintenance-action"} href={action.href} key={action.id}>
            <span>{action.done ? "Op orde" : "Actie"}</span>
            <strong>{action.title}</strong>
            <small>{action.detail}</small>
          </Link>
        ))}
      </div>
    </div>
  );
}

function MaintenanceMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="maintenance-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Log in met een databaseconfiguratie om huisonderhoud lokaal te beheren.</p>
    </div>
  );
}
