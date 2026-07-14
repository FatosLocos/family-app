import Link from "next/link";
import { redirect } from "next/navigation";
import { CalendarDays, CheckSquare, UsersRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { memberName, shortDate } from "@/lib/format";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { buildPeopleWorkloadInsight, type MemberWorkload } from "@/lib/people-workload";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function PeopleWorkPage() {
  const now = new Date().toISOString();
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <PeopleWorkContent data={await getLocalAppData()} now={now} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="dashboard" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <PeopleWorkContent data={data} now={now} />;
}

function PeopleWorkContent({ data, now }: { data: AppData; now: string }) {
  const insight = buildPeopleWorkloadInsight(data, now);

  return (
    <AppShell>
      <CompactModuleHeader
        eyebrow="Dagelijks"
        title="Wie doet wat"
        stats={[
          { label: "gezinsleden", value: data.members.length },
          { label: "open taken", value: insight.openTasks.length },
          { label: "toegewezen", value: insight.totalAssignedTasks },
          { label: "afspraken week", value: insight.upcomingEvents.length },
          { label: "niet toegewezen", value: insight.unassignedTasks.length },
          { label: "rustig", value: insight.quietMembers.length },
        ]}
      >
        Bekijk per gezinslid welke open taken en aankomende afspraken op de radar staan.
      </CompactModuleHeader>

      <section className="people-board section-stack">
        {insight.memberLoads.map((memberLoad) => (
          <MemberCard data={data} memberLoad={memberLoad} key={memberLoad.member.user_id} />
        ))}
        <div className="card member-card">
          <div className="section-head">
            <div>
              <h2>Niet toegewezen</h2>
              <p className="muted">{insight.unassignedTasks.length} open taken zonder eigenaar.</p>
            </div>
            <span className="summary-icon">
              <UsersRound size={18} />
            </span>
          </div>
          <TaskMiniList tasks={insight.unassignedTasks.slice(0, 8)} data={data} />
        </div>
      </section>
    </AppShell>
  );
}

function MemberCard({ data, memberLoad }: { data: AppData; memberLoad: MemberWorkload }) {
  const { member, tasks, events } = memberLoad;

  return (
    <div className="card member-card">
      <div className="section-head">
        <div>
          <h2>{memberName(member.user_id, data.members)}</h2>
          <p className="muted">{roleLabel(member.role)} · {tasks.length} taken · {events.length} afspraken</p>
        </div>
        <span className={`avatar-dot avatar-${member.profile?.avatar_color || "groen"}`}>
          <span>{initials(member.profile?.full_name ?? member.profile?.email ?? "Gezinslid")}</span>
        </span>
      </div>
      <div className="member-work-grid">
        <section>
          <h3><CheckSquare size={15} /> Taken</h3>
          <TaskMiniList tasks={tasks.slice(0, 5)} data={data} />
        </section>
        <section>
          <h3><CalendarDays size={15} /> Agenda</h3>
          <ul className="list compact-list">
            {events.length === 0 && <li className="empty-state">Geen afspraken komende week.</li>}
            {events.slice(0, 5).map((event) => (
              <li className="list-row" key={event.id}>
                <div className="row-main">
                  <div className="row-title">{event.title}</div>
                  <div className="row-meta">{shortDate(event.starts_at)}{event.location ? ` · ${event.location}` : ""}</div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function TaskMiniList({ tasks, data }: { tasks: AppData["tasks"]; data: AppData }) {
  return (
    <ul className="list compact-list">
      {tasks.length === 0 && <li className="empty-state">Geen open taken.</li>}
      {tasks.map((task) => (
        <li className="list-row" key={task.id}>
          <div className="row-main">
            <div className="row-title">{task.title}</div>
            <div className="row-meta">
              {memberName(task.assignee_id, data.members)} · {task.priority} · {shortDate(task.due_date)}
            </div>
          </div>
          <Link className="status" href="/taken">Open</Link>
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

function roleLabel(role: string) {
  if (role === "owner") return "Eigenaar";
  if (role === "admin") return "Beheerder";
  return "Lid";
}

function PeopleMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="people-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}
