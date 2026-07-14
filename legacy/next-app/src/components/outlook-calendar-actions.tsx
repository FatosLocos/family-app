"use client";

import { useState } from "react";
import type { CalendarIntegration } from "@/lib/types";

export function OutlookCalendarActions({ integration }: { integration: CalendarIntegration }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch("/api/outlook-calendar/sync", { method: "POST" });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; count?: number; calendarCount?: number; error?: string };
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? "Synchronisatie mislukt.");
      setMessage(`${payload.count ?? 0} afspraken uit ${payload.calendarCount ?? 0} agenda's.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Synchronisatie mislukt.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
      <a className="button" href="/api/outlook-calendar/oauth/start">
        Outlook autoriseren
      </a>
      <button className="button" onClick={sync} disabled={busy || integration.status === "needs_auth"}>
        {busy ? "Synchroniseren..." : "Synchroniseren"}
      </button>
      {message && <span className="status">{message}</span>}
    </div>
  );
}
