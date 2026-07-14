import { dateKey, dateSortValue } from "@/lib/date-keys";
import { memberName } from "@/lib/format";
import type { AppData, HouseholdMember } from "@/lib/types";

export type MemberWorkload = {
  member: HouseholdMember;
  name: string;
  tasks: AppData["tasks"];
  events: AppData["calendarEvents"];
  load: number;
};

export type PeopleWorkAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type PeopleWorkloadInsight = {
  today: string;
  nextWeek: string;
  openTasks: AppData["tasks"];
  unassignedTasks: AppData["tasks"];
  upcomingEvents: AppData["calendarEvents"];
  memberLoads: MemberWorkload[];
  busiestMember: MemberWorkload | null;
  quietMembers: MemberWorkload[];
  totalAssignedTasks: number;
  score: number;
  totalChecks: number;
  percent: number;
  actions: PeopleWorkAction[];
};

export function buildPeopleWorkloadInsight(data: AppData, nowIso: string): PeopleWorkloadInsight {
  const today = dateKey(nowIso) ?? nowIso.slice(0, 10);
  const nextWeek = addDays(today, 7);
  const openTasks = data.tasks.filter((task) => !task.parent_task_id && task.status === "open");
  const unassignedTasks = openTasks.filter((task) => !task.assignee_id);
  const upcomingEvents = data.calendarEvents.filter((event) => {
    const startsAt = dateKey(event.starts_at);
    return startsAt && startsAt >= today && startsAt <= nextWeek;
  });
  const memberLoads = data.members.map((member) => {
    const tasks = openTasks
      .filter((task) => task.assignee_id === member.user_id)
      .sort((a, b) => dateSortValue(a.due_date) - dateSortValue(b.due_date));
    const events = upcomingEvents
      .filter((event) => event.participant_ids.includes(member.user_id))
      .sort((a, b) => dateSortValue(a.starts_at) - dateSortValue(b.starts_at));
    return {
      member,
      name: memberName(member.user_id, data.members),
      tasks,
      events,
      load: tasks.length + events.length,
    };
  });
  const busiestMember = [...memberLoads].sort((a, b) => b.load - a.load || a.name.localeCompare(b.name))[0] ?? null;
  const quietMembers = memberLoads.filter((item) => item.load === 0);
  const totalAssignedTasks = openTasks.length - unassignedTasks.length;

  const actions: PeopleWorkAction[] = [
    {
      id: "members",
      title: "Gezinsleden aanwezig",
      detail: data.members.length > 1 ? `${data.members.length} gezinsleden actief` : "Nodig gezinsleden uit voor echte verdeling.",
      href: "/instellingen",
      done: data.members.length > 1,
    },
    {
      id: "owners",
      title: "Taken toegewezen",
      detail: unassignedTasks.length === 0 ? "Alle open taken hebben een eigenaar" : `${unassignedTasks.length} taak${unassignedTasks.length === 1 ? "" : "en"} zonder eigenaar`,
      href: "/taken?filter=open",
      done: unassignedTasks.length === 0,
    },
    {
      id: "active",
      title: "Werkverdeling zichtbaar",
      detail: totalAssignedTasks > 0 ? `${totalAssignedTasks} toegewezen taak${totalAssignedTasks === 1 ? "" : "en"}` : "Wijs taken toe aan gezinsleden.",
      href: "/taken",
      done: totalAssignedTasks > 0,
    },
    {
      id: "calendar",
      title: "Afspraken gekoppeld aan leden",
      detail: upcomingEvents.length > 0 ? `${upcomingEvents.length} afspraak${upcomingEvents.length === 1 ? "" : "en"} komende week` : "Geen afspraken komende week.",
      href: "/agenda",
      done: upcomingEvents.length > 0,
    },
    {
      id: "balance",
      title: "Niemand buiten beeld",
      detail: quietMembers.length === 0 ? "Iedereen heeft iets op de radar" : `${quietMembers.length} gezinslid${quietMembers.length === 1 ? "" : "den"} zonder items`,
      href: "/wie-doet-wat",
      done: quietMembers.length === 0,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    today,
    nextWeek,
    openTasks,
    unassignedTasks,
    upcomingEvents,
    memberLoads,
    busiestMember,
    quietMembers,
    totalAssignedTasks,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
  };
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
