import type { AppData } from "@/lib/types";

const redactedKeys = ["password", "password_hash", "token", "secret", "session", "api_key", "client_secret", "refresh_token", "access_token"];

export type ExportPayload = {
  exported_at: string;
  app: "family-app";
  version: 3;
  metadata: {
    app_version: string;
    format: "json";
    restore_mode: "manual";
    redaction: "secret-like-keys";
    source: "app-data-export";
  };
  household_id: string;
  household_name: string;
  summary: {
    total_records: number;
    modules: Record<string, number>;
    excluded_secret_classes: string[];
  };
  data: AppData;
};

export function buildExportPayload(data: AppData, exportedAt: string): ExportPayload {
  const sanitizedData = redactSensitiveKeys(data) as AppData;
  const modules = {
    members: sanitizedData.members.length,
    tasks: sanitizedData.tasks.length,
    shopping_items: sanitizedData.shoppingItems.length,
    shopping_products: sanitizedData.shoppingProducts.length,
    meal_plans: sanitizedData.mealPlans.length,
    finance_items: sanitizedData.financeItems.length,
    finance_budgets: sanitizedData.financeBudgets.length,
    calendar_events: sanitizedData.calendarEvents.length,
    contacts: sanitizedData.householdContacts.length,
    household_info: sanitizedData.householdInfoItems.length,
    documents: sanitizedData.householdDocuments.length,
    maintenance: sanitizedData.maintenanceItems.length,
    notes: sanitizedData.householdNotes.length,
    wishlist_items: sanitizedData.wishlistItems.length,
    wishlist_shares: sanitizedData.wishlistShares.length,
    integrations: sanitizedData.calendarIntegrations.length + sanitizedData.bankConnections.length + sanitizedData.taskIntegrations.length + sanitizedData.smartHomeIntegrations.length,
    smart_home_devices: sanitizedData.smartHomeDevices.length,
  };

  return {
    exported_at: exportedAt,
    app: "family-app",
    version: 3,
    metadata: {
      app_version: "0.1.0",
      format: "json",
      restore_mode: "manual",
      redaction: "secret-like-keys",
      source: "app-data-export",
    },
    household_id: sanitizedData.household.id,
    household_name: sanitizedData.household.name,
    summary: {
      total_records: Object.values(modules).reduce((sum, count) => sum + count, 0),
      modules,
      excluded_secret_classes: redactedKeys,
    },
    data: sanitizedData,
  };
}

export function redactSensitiveKeys(input: unknown): unknown {
  if (Array.isArray(input)) return input.map((item) => redactSensitiveKeys(item));
  if (!input || typeof input !== "object") return input;

  return Object.fromEntries(
    Object.entries(input).map(([key, value]) => {
      if (isSensitiveKey(key)) return [key, "[afgeschermd]"];
      return [key, redactSensitiveKeys(value)];
    }),
  );
}

function isSensitiveKey(key: string) {
  const normalized = key.toLowerCase();
  return redactedKeys.some((pattern) => normalized.includes(pattern));
}
