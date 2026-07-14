import { describe, expect, it } from "vitest";
import { buildAccessReadiness } from "@/lib/access-readiness";
import type { AppData } from "@/lib/types";

const owner = member({ user_id: "owner", role: "owner", profile: { id: "owner", full_name: "Fatih", email: "fatih@example.com", digest_time: "07:30" } });

describe("buildAccessReadiness", () => {
  it("marks a complete access setup as ready", () => {
    const readiness = buildAccessReadiness(
      {
        members: [
          owner,
          member({ user_id: "member", role: "member", profile: { id: "member", full_name: "Gezinslid", email: "gezin@example.com" } }),
        ],
      },
      [],
      [{ id: "session", created_at: "2026-07-11", last_seen_at: "2026-07-11", expires_at: "2026-08-10", is_current: true }],
      "owner",
    );

    expect(readiness.score).toBe(readiness.total);
    expect(readiness.percent).toBe(100);
    expect(readiness.nextAction).toBeNull();
  });

  it("surfaces the first access action that needs attention", () => {
    const readiness = buildAccessReadiness(
      { members: [member({ user_id: "owner", role: "owner", profile: { id: "owner", full_name: null, email: "fatih@example.com" } })] },
      [{ id: "invite-1" }, { id: "invite-2" }, { id: "invite-3" }],
      [
        { id: "current", created_at: "2026-07-11", last_seen_at: "2026-07-11", expires_at: "2026-08-10", is_current: true },
        { id: "other", created_at: "2026-07-10", last_seen_at: "2026-07-10", expires_at: "2026-08-09", is_current: false },
      ],
      "owner",
    );

    expect(readiness.nextAction?.id).toBe("members");
    expect(readiness.incompleteProfiles).toBe(1);
    expect(readiness.openInvites).toBe(3);
    expect(readiness.otherSessions).toBe(1);
  });
});

function member(overrides: Partial<AppData["members"][number]> = {}): AppData["members"][number] {
  return {
    household_id: "hh",
    user_id: "user",
    role: "member",
    profile: { id: "user", full_name: "Gebruiker", email: "user@example.com" },
    ...overrides,
  };
}
