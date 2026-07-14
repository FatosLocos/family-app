import { describe, expect, it } from "vitest";
import { buildEnvironmentReadiness } from "@/lib/environment-readiness";

describe("buildEnvironmentReadiness", () => {
  it("uses local Postgres as primary mode when DATABASE_URL is present", () => {
    const readiness = buildEnvironmentReadiness({
      DATABASE_URL: "postgresql://user:pass@localhost:5432/app",
    });

    expect(readiness.mode).toBe("local_postgres");
    expect(readiness.modeLabel).toBe("Lokale Postgres");
    expect(readiness.requiredReady).toBe(1);
    expect(readiness.nextAction).toBeNull();
  });

  it("stays in demo mode without a PostgreSQL connection", () => {
    const readiness = buildEnvironmentReadiness({});

    expect(readiness.mode).toBe("demo");
    expect(readiness.groups.find((group) => group.id === "local-db")?.ready).toBe(false);
    expect(readiness.nextAction?.id).toBe("local-db");
  });

  it("marks partially configured optional integrations as the next action after required env is ready", () => {
    const readiness = buildEnvironmentReadiness({
      DATABASE_URL: "postgresql://user:pass@localhost:5432/app",
      HUE_BRIDGE_URL: "https://192.168.1.10",
    });

    expect(readiness.mode).toBe("local_postgres");
    expect(readiness.groups.find((group) => group.id === "hue")?.configured).toBe(1);
    expect(readiness.nextAction?.id).toBe("hue");
  });

  it("does not leak secret values into variable statuses", () => {
    const readiness = buildEnvironmentReadiness({
      DATABASE_URL: "postgresql://secret",
      HOME_ASSISTANT_TOKEN: "super-secret-token",
    });
    const variable = readiness.groups.flatMap((group) => group.variables).find((item) => item.key === "HOME_ASSISTANT_TOKEN");

    expect(variable).toEqual({
      key: "HOME_ASSISTANT_TOKEN",
      label: "Long-lived token",
      present: true,
      secret: true,
    });
  });
});
