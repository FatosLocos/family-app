import { describe, expect, it } from "vitest";
import { defaultHouseholdPreferences, normalizeHouseholdPreferencesInput } from "@/lib/household-preferences";

describe("household preferences", () => {
  it("normalizes valid onboarding choices", () => {
    expect(
      normalizeHouseholdPreferencesInput({
        week_starts_on: "sunday",
        default_dashboard: "compact",
        default_shopping_store: "  Jumbo  ",
        quiet_hours_start: "21:30",
        quiet_hours_end: "06:45",
      }),
    ).toEqual({
      week_starts_on: "sunday",
      default_dashboard: "compact",
      default_shopping_store: "Jumbo",
      quiet_hours_start: "21:30",
      quiet_hours_end: "06:45",
    });
  });

  it("falls back to safe defaults for invalid values", () => {
    expect(
      normalizeHouseholdPreferencesInput({
        week_starts_on: "friday",
        default_dashboard: "unknown",
        default_shopping_store: " ",
        quiet_hours_start: "bad",
        quiet_hours_end: "",
      }),
    ).toEqual({
      week_starts_on: "monday",
      default_dashboard: "vandaag",
      default_shopping_store: null,
      quiet_hours_start: null,
      quiet_hours_end: null,
    });
  });

  it("provides app defaults for a new household", () => {
    expect(defaultHouseholdPreferences("household-1")).toEqual({
      household_id: "household-1",
      week_starts_on: "monday",
      default_dashboard: "vandaag",
      default_shopping_store: null,
      quiet_hours_start: "22:00",
      quiet_hours_end: "07:00",
    });
  });
});
