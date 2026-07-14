import { redirect } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, CalendarClock, CheckCircle2, Scale, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { TaskForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { ModuleLayout } from "@/components/module-layout";
import { TaskIntegrationsPanel, TaskList } from "@/components/module-lists";
import { getAppData, getUser } from "@/lib/local-data";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { dateKey, dateSortValue } from "@/lib/date-keys";
import { memberName, shortDate } from "@/lib/format";
import { filterTasks, normalizeTaskFilter } from "@/lib/task-filters";
import { demoData } from "@/lib/demo-data";
import type { AppData } from "@/lib/types";

const filters = [
  { href: "/taken?filter=open", label: "Open" },
  { href: "/taken?filter=vandaag", label: "Vandaag" },
  { href: "/taken?filter=alles", label: "Alles" },
];

export const dynamic = "force-dynamic";

export default async function TasksPage({
  searchParams,
}: {
  searchParams?: Promise<{ filter?: string | string[] }>;
}) {
  const query = await searchParams;
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <TasksContent data={await getLocalAppData()} activeFilter={normalizeTaskFilter(query?.filter)} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="taken" filter={normalizeTaskFilter(query?.filter)} />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <TasksContent data={data} activeFilter={normalizeTaskFilter(query?.filter)} />;
}

function TasksContent({ data, activeFilter, demo = false }: { data: typeof demoData; activeFilter: ReturnType<typeof normalizeTaskFilter>; demo?: boolean }) {
  const tasks = filterTasks(data.tasks, activeFilter);
  const now = new Date().toISOString();
  const today = now.slice(0, 10);
  const openTasks = data.tasks.filter((task) => task.status === "open" && !task.parent_task_id);
  const dueToday = openTasks.filter((task) => dateKey(task.due_date) === today);
  const overdue = openTasks.filter((task) => dateKey(task.due_date) !== null && dateKey(task.due_date)! < today);
  const unassigned = openTasks.filter((task) => !task.assignee_id);

  return (
    <AppShell demo={demo}>
      <ModuleLayout
        asideLabel="Takenacties"
        aside={demo ? <DemoPanel /> : <><ModuleSubmenu title="Taak toevoegen" detail="Nieuwe taak, eigenaar en deadline vastleggen"><TaskForm members={data.members} /></ModuleSubmenu><TaskIntegrationsPanel data={data} /></>}
      >
        <div className="grid">
          <div className="grid" style={{ gap: 12 }}>
            <CompactModuleHeader
              eyebrow="Dagelijks"
              title="Taken"
              stats={[
                { label: "zichtbaar", value: tasks.length },
                { label: "open", value: openTasks.length },
                { label: "vandaag", value: dueToday.length },
                { label: "te laat", value: overdue.length },
                { label: "zonder eigenaar", value: unassigned.length },
              ]}
            >
              Taken, deadlines en verdeling in een schoon overzicht.
            </CompactModuleHeader>
            <div className="nav" aria-label="Taakfilters">
              {filters.map((filter) => (
                <a
                  key={filter.href}
                  href={filter.href}
                  aria-current={filter.href.endsWith(activeFilter) ? "page" : undefined}
                  style={filter.href.endsWith(activeFilter) ? { borderColor: "var(--primary)", color: "var(--primary-strong)" } : undefined}
                >
                  {filter.label}
                </a>
              ))}
            </div>
          </div>
          <TaskList data={data} tasks={tasks} readOnly={demo} />
        </div>
      </ModuleLayout>
    </AppShell>
  );
}

function TaskControlPanel({ data, now }: { data: AppData; now: string }) {
  const today = now.slice(0, 10);
  const open = data.tasks.filter((task) => task.status === "open" && !task.parent_task_id);
  const overdue = open.filter((task) => dateKey(task.due_date) !== null && dateKey(task.due_date)! < today);
  const dueToday = open.filter((task) => dateKey(task.due_date) === today);
  const high = open.filter((task) => task.priority === "hoog");
  const unassigned = open.filter((task) => !task.assignee_id);
  const recurring = open.filter((task) => task.recurrence && task.recurrence !== "none");
  const completed = data.tasks.filter((task) => task.status === "done" && !task.parent_task_id).length;
  const completionRate = data.tasks.filter((task) => !task.parent_task_id).length === 0
    ? 100
    : Math.round((completed / data.tasks.filter((task) => !task.parent_task_id).length) * 100);
  const nextTask = [...open]
    .filter((task) => task.due_date)
    .sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date))[0];
  const memberLoad = data.members
    .map((member) => ({
      id: member.user_id,
      name: member.profile?.full_name ?? member.profile?.email ?? "Gezinslid",
      count: open.filter((task) => task.assignee_id === member.user_id).length,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const maxLoad = Math.max(1, ...memberLoad.map((member) => member.count));
  const busiest = memberLoad[0];
  const quietest = [...memberLoad].reverse().find((member) => member.count === 0) ?? memberLoad[memberLoad.length - 1];
  const nextAction = overdue[0]
    ? {
        title: `${overdue[0].title} is over tijd`,
        detail: `${memberName(overdue[0].assignee_id, data.members)} · deadline ${shortDate(overdue[0].due_date)}`,
        href: "/taken?filter=open",
        tone: "urgent" as const,
      }
    : dueToday[0]
      ? {
          title: `${dueToday[0].title} staat voor vandaag`,
          detail: `${memberName(dueToday[0].assignee_id, data.members)} · ${dueToday.length} taak${dueToday.length === 1 ? "" : "en"} vandaag`,
          href: "/taken?filter=vandaag",
          tone: "attention" as const,
        }
      : unassigned[0]
        ? {
            title: `${unassigned[0].title} mist eigenaar`,
            detail: "Wijs deze toe zodat hij ook in Wie doet wat zichtbaar wordt.",
            href: "/wie-doet-wat",
            tone: "attention" as const,
          }
        : nextTask
          ? {
              title: nextTask.title,
              detail: `${memberName(nextTask.assignee_id, data.members)} · ${shortDate(nextTask.due_date)}`,
              href: "/taken?filter=open",
              tone: "calm" as const,
            }
          : {
              title: "Geen directe taakdruk",
              detail: recurring.length > 0 ? `${recurring.length} terugkerende taken blijven actief.` : "Maak nieuwe taken aan zodra er iets speelt.",
              href: "/snel",
              tone: "calm" as const,
            };

  return (
    <div className="task-control card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Regie</span>
          <h2>Takenregie</h2>
          <p className="muted">Prioriteit, verdeling en eerstvolgende actie voor het huishouden.</p>
        </div>
        <span className={overdue.length > 0 ? "status accent" : "status"}>{overdue.length} over tijd</span>
      </div>
      <div className="task-control-grid">
        <TaskMetric icon={<CheckCircle2 size={17} />} label="Open" value={open.length} detail={`${completionRate}% afgerond`} href="/taken?filter=open" />
        <TaskMetric icon={<CalendarClock size={17} />} label="Vandaag" value={dueToday.length} detail={`${overdue.length} over tijd`} href="/taken?filter=vandaag" />
        <TaskMetric icon={<AlertTriangle size={17} />} label="Hoog" value={high.length} detail="Hoge prioriteit open" href="/taken?filter=open" />
        <TaskMetric icon={<UserRound size={17} />} label="Niet toegewezen" value={unassigned.length} detail="Mist eigenaar" href="/wie-doet-wat" />
      </div>
      <div className="task-load-row">
        <div>
          <strong>{nextAction.title}</strong>
          <p className="muted">{nextAction.detail}</p>
          <div className="task-focus-actions">
            <Link className={nextAction.tone === "urgent" ? "button primary" : "button"} href={nextAction.href}>Open focus</Link>
            <span className="status">{recurring.length} terugkerend</span>
          </div>
        </div>
        <div className="task-balance-card">
          <div className="task-balance-head">
            <span><Scale size={16} /> Werkverdeling</span>
            <strong>{busiest ? `${busiest.name}: ${busiest.count}` : "Geen taken"}</strong>
          </div>
          <div className="task-member-bars">
            {memberLoad.length === 0 ? (
              <span className="muted">Nog geen gezinsleden om taken aan te koppelen.</span>
            ) : (
              memberLoad.map((member) => (
                <div className="task-member-bar" key={member.id}>
                  <div>
                    <span>{member.name}</span>
                    <strong>{member.count}</strong>
                  </div>
                  <div className="progress-track" aria-label={`${member.name} ${member.count} open taken`}>
                    <span className="progress-fill" style={{ width: `${Math.max(4, Math.round((member.count / maxLoad) * 100))}%` }} />
                  </div>
                </div>
              ))
            )}
          </div>
          <p className="muted">{quietest && busiest && busiest.count > quietest.count + 2 ? `${quietest.name} heeft ruimte om werk over te nemen.` : "De verdeling is rustig genoeg."}</p>
        </div>
      </div>
    </div>
  );
}

function TaskMetric({ icon, label, value, detail, href }: { icon: ReactNode; label: string; value: number; detail: string; href: string }) {
  return (
    <a className="task-metric" href={href}>
      <span className="task-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </a>
  );
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Configureer PostgreSQL om taken echt toe te voegen, af te vinken en te verwijderen.</p>
    </div>
  );
}
