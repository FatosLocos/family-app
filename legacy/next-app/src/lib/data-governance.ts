import type { AppData } from "@/lib/types";

export type DataModuleCount = {
  key: string;
  label: string;
  count: number;
};

export type IntegrationStatus = {
  label: string;
  active: boolean;
};

export type BackupAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type DataGovernanceInsight = {
  counts: DataModuleCount[];
  totalRecords: number;
  activeModuleCount: number;
  sensitiveDocuments: number;
  sensitiveInfo: number;
  sensitiveTotal: number;
  emergencyContacts: number;
  integrations: IntegrationStatus[];
  activeIntegrations: number;
  backupActions: BackupAction[];
  backupScore: number;
  backupTotal: number;
  backupPercent: number;
  nextAction: BackupAction | null;
  exportVersion: 3;
};

export function buildDataGovernanceInsight(data: AppData): DataGovernanceInsight {
  const counts: DataModuleCount[] = [
    { key: "members", label: "Gezinsleden", count: data.members.length },
    { key: "tasks", label: "Taken", count: data.tasks.length },
    { key: "shopping_items", label: "Boodschappen", count: data.shoppingItems.length },
    { key: "shopping_products", label: "Producten", count: data.shoppingProducts.length },
    { key: "meal_plans", label: "Maaltijden", count: data.mealPlans.length },
    { key: "calendar_events", label: "Afspraken", count: data.calendarEvents.length },
    { key: "finance_items", label: "Gelditems", count: data.financeItems.length },
    { key: "documents", label: "Documenten", count: data.householdDocuments.length },
    { key: "contacts", label: "Contacten", count: data.householdContacts.length },
    { key: "household_info", label: "Huisinfo", count: data.householdInfoItems.length },
    { key: "maintenance", label: "Onderhoud", count: data.maintenanceItems.length },
    { key: "smart_home_devices", label: "Smart home apparaten", count: data.smartHomeDevices.length },
    { key: "wishlist_items", label: "Wensen", count: data.wishlistItems.length },
    { key: "wishlist_shares", label: "Wishlist deel-links", count: data.wishlistShares.length },
  ];
  const totalRecords = counts.reduce((sum, item) => sum + item.count, 0);
  const sensitiveDocuments = data.householdDocuments.filter((document) => document.is_sensitive).length;
  const sensitiveInfo = data.householdInfoItems.filter((item) => item.is_sensitive).length;
  const emergencyContacts = data.householdContacts.filter((contact) => contact.priority === "nood").length;
  const integrations: IntegrationStatus[] = [
    { label: "Home Assistant", active: data.hasHomeAssistantConfig },
    { label: "Hue", active: data.hasHueConfig },
    { label: "Google Home", active: data.smartHomeIntegrations.length > 0 },
    { label: "Agenda", active: data.calendarIntegrations.length + (data.icsCalendarSubscriptions?.length ?? 0) + (data.icsCalendarFileImports?.length ?? 0) > 0 },
    { label: "Bunq", active: data.bankConnections.length > 0 },
    { label: "Taken", active: data.taskIntegrations.length > 0 },
  ];
  const activeIntegrations = integrations.filter((item) => item.active).length;
  const backupActions: BackupAction[] = [
    {
      id: "records",
      title: "Gezinsdata aanwezig",
      detail: totalRecords > 0 ? `${totalRecords} records beschikbaar voor export.` : "Vul eerst modules zodat een export waarde heeft.",
      href: "/inrichting",
      done: totalRecords > 0,
    },
    {
      id: "sensitive-labels",
      title: "Gevoelige gegevens gelabeld",
      detail: sensitiveDocuments + sensitiveInfo > 0 ? `${sensitiveDocuments + sensitiveInfo} gevoelige items gemarkeerd.` : "Markeer documenten of huisinfo die niet breed zichtbaar moeten zijn.",
      href: "/documenten",
      done: sensitiveDocuments + sensitiveInfo > 0,
    },
    {
      id: "integrations",
      title: "Koppelingen bekend",
      detail: activeIntegrations > 0 ? `${activeIntegrations} koppeling${activeIntegrations === 1 ? "" : "en"} actief of gepland.` : "Koppel agenda, bank of smart home zodra je die data wilt meenemen.",
      href: "/koppelingen",
      done: activeIntegrations > 0,
    },
    {
      id: "secret-redaction",
      title: "Secrets afgeschermd",
      detail: "Export maskeert token-, secret-, sessie- en API-key-achtige velden.",
      href: "/data",
      done: true,
    },
    {
      id: "json-v3",
      title: "JSON export v3",
      detail: "Export bevat metadata, module-aantallen en gesaneerde appdata.",
      href: "/api/export",
      done: true,
    },
  ];
  const backupScore = backupActions.filter((item) => item.done).length;

  return {
    counts,
    totalRecords,
    activeModuleCount: counts.filter((item) => item.count > 0).length,
    sensitiveDocuments,
    sensitiveInfo,
    sensitiveTotal: sensitiveDocuments + sensitiveInfo,
    emergencyContacts,
    integrations,
    activeIntegrations,
    backupActions,
    backupScore,
    backupTotal: backupActions.length,
    backupPercent: Math.round((backupScore / backupActions.length) * 100),
    nextAction: backupActions.find((item) => !item.done) ?? null,
    exportVersion: 3,
  };
}
