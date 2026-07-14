import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildExportPayload, redactSensitiveKeys } from "@/lib/export";

describe("buildExportPayload", () => {
  it("adds export metadata and record summary", () => {
    const payload = buildExportPayload(demoData, "2026-07-11T10:00:00.000Z");

    expect(payload.version).toBe(3);
    expect(payload.metadata.restore_mode).toBe("manual");
    expect(payload.household_id).toBe(demoData.household.id);
    expect(payload.summary.modules.tasks).toBe(demoData.tasks.length);
    expect(payload.summary.modules.documents).toBe(demoData.householdDocuments.length);
    expect(payload.summary.total_records).toBeGreaterThan(0);
  });

  it("redacts nested secret-like keys before export", () => {
    const payload = buildExportPayload(
      {
        ...demoData,
        smartHomeIntegrations: [
          {
            ...demoData.smartHomeIntegrations[0],
            client_secret: "secret-value",
            access_token: "token-value",
          } as (typeof demoData.smartHomeIntegrations)[number] & { client_secret: string; access_token: string },
        ],
      },
      "2026-07-11T10:00:00.000Z",
    );

    const text = JSON.stringify(payload);
    expect(text).not.toContain("secret-value");
    expect(text).not.toContain("token-value");
    expect(text).toContain("[afgeschermd]");
  });
});

describe("redactSensitiveKeys", () => {
  it("redacts recursive sensitive keys and leaves normal values intact", () => {
    const result = redactSensitiveKeys({
      title: "Gezinsdata",
      nested: {
        session_token: "session",
        api_key: "key",
        value: "zichtbaar",
      },
    });

    expect(result).toEqual({
      title: "Gezinsdata",
      nested: {
        session_token: "[afgeschermd]",
        api_key: "[afgeschermd]",
        value: "zichtbaar",
      },
    });
  });
});
