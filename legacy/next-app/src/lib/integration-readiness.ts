import type { AppData } from "@/lib/types";

export type IntegrationStatus = "configured" | "needs_auth" | "needs_session" | "planned" | "sync_error" | "missing";

export type IntegrationCardData = {
  id: string;
  title: string;
  detail: string;
  status: IntegrationStatus;
  href: string;
  module: "Agenda" | "Geld" | "Taken" | "Smart home";
  lastSync?: string | null;
};

export type IntegrationDomain = {
  label: "Planning" | "Geld" | "Smart home";
  cards: IntegrationCardData[];
  active: number;
  total: number;
  percent: number;
};

export type IntegrationReadiness = {
  cards: IntegrationCardData[];
  configured: number;
  attention: number;
  missing: number;
  planned: number;
  total: number;
  latestSync: IntegrationCardData | null;
  domains: IntegrationDomain[];
  nextAttention: IntegrationCardData | null;
  percent: number;
};

export function buildIntegrationReadiness(data: AppData): IntegrationReadiness {
  const cards = buildIntegrationCards(data);
  const configured = cards.filter((card) => card.status === "configured").length;
  const attention = cards.filter((card) => isAttentionStatus(card.status)).length;
  const missing = cards.filter((card) => card.status === "missing").length;
  const planned = cards.filter((card) => card.status === "planned").length;
  const withSync = cards.filter((card) => card.lastSync).sort((a, b) => String(b.lastSync).localeCompare(String(a.lastSync)));
  const domains = buildDomains(cards);

  return {
    cards,
    configured,
    attention,
    missing,
    planned,
    total: cards.length,
    latestSync: withSync[0] ?? null,
    domains,
    nextAttention: cards.find((card) => card.status === "sync_error" || card.status === "needs_auth" || card.status === "needs_session" || card.status === "missing") ?? null,
    percent: cards.length === 0 ? 0 : Math.round((configured / cards.length) * 100),
  };
}

export function buildIntegrationCards(data: AppData): IntegrationCardData[] {
  const outlook = data.calendarIntegrations[0];
  const ics = data.icsCalendarSubscriptions?.[0];
  const icsFile = data.icsCalendarFileImports?.[0];
  const bank = data.bankConnections[0];
  const taskIntegration = data.taskIntegrations[0];
  const googleHome = data.smartHomeIntegrations[0];

  return [
    {
      id: "outlook",
      title: "Outlook agenda",
      detail: outlook ? `${outlook.display_name}${outlook.account_email ? ` · ${outlook.account_email}` : ""}` : "Nog geen Outlook agenda gekoppeld.",
      status: outlook?.status ?? "missing",
      href: "/instellingen",
      module: "Agenda",
      lastSync: outlook?.last_sync_at,
    },
    {
      id: "ics",
      title: "ICS agenda",
      detail: ics ? ics.display_name : icsFile ? `${icsFile.display_name} · bestand` : "Nog geen ICS-agenda gekoppeld.",
      status: ics?.status ?? icsFile?.status ?? "missing",
      href: "/agenda",
      module: "Agenda",
      lastSync: ics?.last_sync_at ?? icsFile?.last_imported_at,
    },
    {
      id: "bunq",
      title: "bunq bank",
      detail: bank ? `${bank.environment} · ${data.bankAccounts.length} rekening${data.bankAccounts.length === 1 ? "" : "en"}` : "Nog geen bankkoppeling actief.",
      status: bank?.status ?? "missing",
      href: "/geld",
      module: "Geld",
      lastSync: bank?.last_sync_at,
    },
    {
      id: "tasks",
      title: "Taken-apps",
      detail: taskIntegration ? `${taskIntegration.display_name} · ${taskIntegration.sync_direction}` : "Microsoft To Do en Apple Herinneringen staan nog niet actief.",
      status: taskIntegration?.status ?? "missing",
      href: "/instellingen",
      module: "Taken",
      lastSync: taskIntegration?.last_sync_at,
    },
    {
      id: "home-assistant",
      title: "Home Assistant",
      detail: data.hasHomeAssistantConfig ? "Server-side configuratie is aanwezig." : "Nog geen Home Assistant configuratie.",
      status: data.hasHomeAssistantConfig ? "configured" : "missing",
      href: "/home",
      module: "Smart home",
    },
    {
      id: "hue",
      title: "Philips Hue",
      detail: data.hasHueConfig ? "Hue bridge is gekoppeld." : "Nog geen Hue bridge gekoppeld.",
      status: data.hasHueConfig ? "configured" : "missing",
      href: "/home",
      module: "Smart home",
    },
    {
      id: "google-home",
      title: "Google Home",
      detail: googleHome ? `${googleHome.display_name} · ${googleHome.mode}` : "Nog geen Google Home/Nest koppeling actief.",
      status: googleHome?.status ?? "missing",
      href: "/home",
      module: "Smart home",
      lastSync: googleHome?.last_sync_at,
    },
  ];
}

function buildDomains(cards: IntegrationCardData[]): IntegrationDomain[] {
  return [
    buildDomain("Planning", cards.filter((card) => card.module === "Agenda" || card.module === "Taken")),
    buildDomain("Geld", cards.filter((card) => card.module === "Geld")),
    buildDomain("Smart home", cards.filter((card) => card.module === "Smart home")),
  ];
}

function buildDomain(label: IntegrationDomain["label"], cards: IntegrationCardData[]) {
  const active = cards.filter((card) => card.status === "configured").length;
  return {
    label,
    cards,
    active,
    total: cards.length,
    percent: cards.length === 0 ? 0 : Math.round((active / cards.length) * 100),
  };
}

function isAttentionStatus(status: IntegrationStatus) {
  return status === "needs_auth" || status === "needs_session" || status === "sync_error";
}
