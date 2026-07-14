import type { HouseholdPreferences } from "@/lib/types";

export type HouseholdPreferenceInput = {
  week_starts_on?: string | null;
  default_dashboard?: string | null;
  default_shopping_store?: string | null;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
};

export function normalizeHouseholdPreferencesInput(input: HouseholdPreferenceInput): Omit<HouseholdPreferences, "household_id" | "updated_at"> {
  return {
    week_starts_on: input.week_starts_on === "sunday" ? "sunday" : "monday",
    default_dashboard:
      input.default_dashboard === "compact" || input.default_dashboard === "uitgebreid"
        ? input.default_dashboard
        : "vandaag",
    default_shopping_store: cleanOptionalText(input.default_shopping_store),
    quiet_hours_start: normalizeTimePreference(input.quiet_hours_start),
    quiet_hours_end: normalizeTimePreference(input.quiet_hours_end),
  };
}

export function defaultHouseholdPreferences(householdId: string): HouseholdPreferences {
  return {
    household_id: householdId,
    week_starts_on: "monday",
    default_dashboard: "vandaag",
    default_shopping_store: null,
    quiet_hours_start: "22:00",
    quiet_hours_end: "07:00",
  };
}

function cleanOptionalText(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function normalizeTimePreference(time: string | null | undefined) {
  if (!time) return null;
  return /^\d{2}:\d{2}$/.test(time) ? time : null;
}
