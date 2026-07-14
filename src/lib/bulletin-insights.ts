import { dateKey, dateSortValue } from "@/lib/date-keys";
import { shortDate } from "@/lib/format";
import type { AppData, HouseholdNote } from "@/lib/types";

export type BulletinAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type BulletinInsight = {
  total: number;
  pinnedNotes: HouseholdNote[];
  expiring: HouseholdNote[];
  expired: HouseholdNote[];
  categories: string[];
  latest: HouseholdNote | null;
  emptyBody: HouseholdNote[];
  attentionCount: number;
  score: number;
  totalChecks: number;
  percent: number;
  actions: BulletinAction[];
  nextAction: BulletinAction;
};

export function buildBulletinInsight(data: AppData, today = new Date().toISOString().slice(0, 10)): BulletinInsight {
  const todayKey = dateKey(today) ?? today;
  const nextWeek = addDays(todayKey, 7);
  const pinnedNotes = data.householdNotes.filter((note) => note.pinned);
  const expiring = data.householdNotes
    .filter((note) => {
      const expiresAt = dateKey(note.expires_at);
      return expiresAt && expiresAt >= todayKey && expiresAt <= nextWeek;
    })
    .sort((a, b) => dateSortValue(a.expires_at) - dateSortValue(b.expires_at));
  const expired = data.householdNotes
    .filter((note) => {
      const expiresAt = dateKey(note.expires_at);
      return expiresAt && expiresAt < todayKey;
    })
    .sort((a, b) => dateSortValue(a.expires_at) - dateSortValue(b.expires_at));
  const categories = Array.from(new Set(data.householdNotes.map((note) => note.category).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  const latest = [...data.householdNotes].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null;
  const emptyBody = data.householdNotes.filter((note) => note.body.trim().length < 12);
  const attentionCount = pinnedNotes.length + expiring.length + expired.length;

  const actions: BulletinAction[] = [
    {
      id: "baseline",
      title: "Prikbord gestart",
      detail: data.householdNotes.length > 0 ? `${data.householdNotes.length} bericht${data.householdNotes.length === 1 ? "" : "en"} geplaatst` : "Plaats je eerste gezinsbericht.",
      href: "/prikbord",
      done: data.householdNotes.length > 0,
    },
    {
      id: "pinned",
      title: "Belangrijk bericht vastgezet",
      detail: pinnedNotes.length > 0 ? `${pinnedNotes.length} bericht${pinnedNotes.length === 1 ? "" : "en"} vastgezet` : "Zet minimaal een belangrijk bericht vast.",
      href: "/prikbord",
      done: pinnedNotes.length > 0,
    },
    {
      id: "expired",
      title: "Geen verlopen berichten",
      detail: expired.length === 0 ? "Geen verlopen notities zichtbaar" : `${expired.length} verlopen bericht${expired.length === 1 ? "" : "en"} opruimen`,
      href: "/prikbord",
      done: expired.length === 0,
    },
    {
      id: "temporary",
      title: "Tijdelijke berichten met einddatum",
      detail: expiring.length > 0 ? `${expiring.length} bericht${expiring.length === 1 ? "" : "en"} loopt binnenkort af` : "Gebruik einddatums voor tijdelijke reminders.",
      href: "/prikbord",
      done: expiring.length > 0 || data.householdNotes.some((note) => Boolean(note.expires_at)),
    },
    {
      id: "categories",
      title: "Categorieën gebruikt",
      detail: categories.length >= 2 ? `${categories.length} categorieën actief` : "Gebruik categorieën zoals Huis, School of Sport.",
      href: "/prikbord",
      done: categories.length >= 2,
    },
    {
      id: "content",
      title: "Berichten zijn duidelijk",
      detail: emptyBody.length === 0 ? "Alle berichten hebben voldoende tekst" : `${emptyBody.length} bericht${emptyBody.length === 1 ? "" : "en"} zijn erg kort`,
      href: "/prikbord",
      done: emptyBody.length === 0,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    total: data.householdNotes.length,
    pinnedNotes,
    expiring,
    expired,
    categories,
    latest,
    emptyBody,
    attentionCount,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
    nextAction: actions.find((action) => !action.done) ?? {
      id: "today",
      title: "Prikbord is op orde",
      detail: latest ? `${latest.title} is geplaatst op ${shortDate(latest.created_at)}.` : "Bekijk Vandaag voor de actuele gezinsregie.",
      href: "/vandaag",
      done: true,
    },
  };
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
