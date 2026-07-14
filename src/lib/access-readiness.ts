import type { AppData } from "@/lib/types";

export type SessionSummary = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  is_current: boolean;
};

export type AccessAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
  tone: "ok" | "attention";
};

export type AccessReadiness = {
  admins: number;
  incompleteProfiles: number;
  emailNotifications: number;
  openInvites: number;
  otherSessions: number;
  score: number;
  total: number;
  percent: number;
  actions: AccessAction[];
  nextAction: AccessAction | null;
};

export function buildAccessReadiness(
  data: Pick<AppData, "members">,
  invites: Array<{ id: string }>,
  sessions: SessionSummary[],
  currentUserId?: string,
): AccessReadiness {
  const admins = data.members.filter((member) => member.role === "owner" || member.role === "admin").length;
  const incompleteProfiles = data.members.filter((member) => !member.profile?.full_name || !member.profile?.email).length;
  const emailNotifications = data.members.filter((member) => member.profile?.notification_email !== false).length;
  const currentMember = data.members.find((member) => member.user_id === currentUserId);
  const currentProfile = currentMember?.profile;
  const otherSessions = sessions.filter((session) => !session.is_current).length;
  const actions: AccessAction[] = [
    {
      id: "members",
      title: "Gezinsleden actief",
      detail: data.members.length > 1 ? `${data.members.length} gezinsleden hebben toegang.` : "Nodig gezinsleden uit voor eigen accounts.",
      href: "/instellingen",
      done: data.members.length > 1,
      tone: data.members.length > 1 ? "ok" : "attention",
    },
    {
      id: "admins",
      title: "Beheerder aanwezig",
      detail: admins > 0 ? `${admins} beheerder${admins === 1 ? "" : "s"} ingesteld.` : "Maak minimaal een eigenaar of beheerder actief.",
      href: "/instellingen",
      done: admins > 0,
      tone: admins > 0 ? "ok" : "attention",
    },
    {
      id: "profiles",
      title: "Profielen compleet",
      detail: incompleteProfiles === 0 ? "Alle leden hebben naam en e-mail." : `${incompleteProfiles} profiel${incompleteProfiles === 1 ? "" : "en"} mist basisgegevens.`,
      href: "/instellingen",
      done: incompleteProfiles === 0,
      tone: incompleteProfiles === 0 ? "ok" : "attention",
    },
    {
      id: "invites",
      title: "Open invites beperkt",
      detail: invites.length <= 2 ? `${invites.length} open invite${invites.length === 1 ? "" : "s"}.` : "Trek oude invite-codes in om toegang overzichtelijk te houden.",
      href: "/instellingen",
      done: invites.length <= 2,
      tone: invites.length <= 2 ? "ok" : "attention",
    },
    {
      id: "digest",
      title: "Dagoverzicht gekozen",
      detail: currentProfile?.digest_time ? `Dagoverzicht staat op ${currentProfile.digest_time}.` : "Kies een tijdstip voor je persoonlijke dagoverzicht.",
      href: "/instellingen",
      done: Boolean(currentProfile?.digest_time),
      tone: currentProfile?.digest_time ? "ok" : "attention",
    },
    {
      id: "sessions",
      title: "Sessies gecontroleerd",
      detail: otherSessions === 0 ? "Geen andere actieve sessies." : `${otherSessions} andere sessie${otherSessions === 1 ? "" : "s"} actief.`,
      href: "/instellingen",
      done: otherSessions === 0,
      tone: otherSessions === 0 ? "ok" : "attention",
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    admins,
    incompleteProfiles,
    emailNotifications,
    openInvites: invites.length,
    otherSessions,
    score,
    total: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
    nextAction: actions.find((action) => !action.done) ?? null,
  };
}
