import { buildNotifications, type NotificationItem } from "@/lib/notifications";
import type { AppData } from "@/lib/types";

export type NotificationModuleCount = {
  module: NotificationItem["module"];
  count: number;
};

export type NotificationInsight = {
  notifications: NotificationItem[];
  urgent: NotificationItem[];
  attention: NotificationItem[];
  info: NotificationItem[];
  todayItems: NotificationItem[];
  tomorrowItems: NotificationItem[];
  overdueItems: NotificationItem[];
  setupItems: NotificationItem[];
  moduleCounts: NotificationModuleCount[];
  topAction: NotificationItem | null;
  busiestModule: NotificationModuleCount | null;
  pressureScore: number;
  briefingTone: NotificationItem["tone"];
  quiet: boolean;
  digest: NotificationDigest;
};

export type NotificationDigestRecipient = {
  id: string;
  name: string;
  email: string | null;
  time: string | null;
  enabled: boolean;
};

export type NotificationDigest = {
  recipients: NotificationDigestRecipient[];
  enabledRecipients: NotificationDigestRecipient[];
  nextTime: string | null;
  subject: string;
  previewItems: NotificationItem[];
  ready: boolean;
};

export function buildNotificationInsight(data: AppData, nowIso: string): NotificationInsight {
  const notifications = buildNotifications(data, nowIso);
  const urgent = notifications.filter((item) => item.tone === "urgent");
  const attention = notifications.filter((item) => item.tone === "attention");
  const info = notifications.filter((item) => item.tone === "info");
  const todayItems = notifications.filter((item) => item.dueLabel === "Vandaag");
  const tomorrowItems = notifications.filter((item) => item.dueLabel === "Morgen");
  const overdueItems = notifications.filter((item) => item.dueLabel === "Te laat");
  const setupItems = notifications.filter((item) => item.dueLabel === "Setup");
  const moduleCounts = countByModule(notifications);
  const topAction = urgent[0] ?? attention[0] ?? notifications[0] ?? null;
  const busiestModule = moduleCounts[0] ?? null;
  const pressureScore = Math.min(100, urgent.length * 30 + attention.length * 12 + info.length * 4);
  const digest = buildNotificationDigest(data, notifications, urgent, attention, nowIso);

  return {
    notifications,
    urgent,
    attention,
    info,
    todayItems,
    tomorrowItems,
    overdueItems,
    setupItems,
    moduleCounts,
    topAction,
    busiestModule,
    pressureScore,
    briefingTone: urgent.length > 0 ? "urgent" : attention.length > 0 ? "attention" : "info",
    quiet: notifications.length === 0 || (urgent.length === 0 && attention.length === 0),
    digest,
  };
}

export function buildNotificationDigest(
  data: AppData,
  notifications: NotificationItem[],
  urgent: NotificationItem[],
  attention: NotificationItem[],
  nowIso: string,
): NotificationDigest {
  const recipients = data.members.map((member) => ({
    id: member.user_id,
    name: member.profile?.full_name || member.profile?.email || "Gezinslid",
    email: member.profile?.email ?? null,
    time: member.profile?.digest_time ?? null,
    enabled: member.profile?.notification_email !== false && Boolean(member.profile?.email),
  }));
  const enabledRecipients = recipients.filter((recipient) => recipient.enabled);
  const nextTime = nextDigestTime(enabledRecipients, nowIso);
  const previewItems = [
    ...urgent,
    ...attention,
    ...notifications.filter((item) => item.tone === "info"),
  ].filter(uniqueById).slice(0, 6);
  const subject = urgent.length > 0
    ? `${urgent.length} urgente melding${urgent.length === 1 ? "" : "en"} voor je huishouden`
    : attention.length > 0
      ? `${attention.length} aandachtspunt${attention.length === 1 ? "" : "en"} voor vandaag`
      : "Dagoverzicht: alles rustig";

  return {
    recipients,
    enabledRecipients,
    nextTime,
    subject,
    previewItems,
    ready: enabledRecipients.length > 0 && Boolean(nextTime),
  };
}

function countByModule(items: NotificationItem[]) {
  const counts = new Map<NotificationItem["module"], number>();
  items.forEach((item) => counts.set(item.module, (counts.get(item.module) ?? 0) + 1));
  return Array.from(counts.entries())
    .map(([module, count]) => ({ module, count }))
    .sort((a, b) => b.count - a.count || a.module.localeCompare(b.module));
}

function nextDigestTime(recipients: NotificationDigestRecipient[], nowIso: string) {
  const times = recipients
    .map((recipient) => recipient.time)
    .filter((time): time is string => Boolean(time))
    .sort();
  if (times.length === 0) return null;
  const now = new Date(nowIso);
  const today = nowIso.slice(0, 10);
  const currentMinutes = now.getHours() * 60 + now.getMinutes();
  const todayTime = times.find((time) => minutes(time) >= currentMinutes);
  if (todayTime) return `${todayTime} vandaag`;
  return `${times[0]} morgen`;
}

function minutes(time: string) {
  const [hours, minutesValue] = time.split(":").map(Number);
  return (Number.isFinite(hours) ? hours : 0) * 60 + (Number.isFinite(minutesValue) ? minutesValue : 0);
}

function uniqueById(item: NotificationItem, index: number, items: NotificationItem[]) {
  return items.findIndex((candidate) => candidate.id === item.id) === index;
}
