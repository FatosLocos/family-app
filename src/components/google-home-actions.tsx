"use client";

import { useState } from "react";
import type { SmartHomeIntegration } from "@/lib/types";

export function GoogleHomeActions({ integration }: { integration: SmartHomeIntegration }) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch("/api/google-home/sync", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode: integration.mode }),
      });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; count?: number; error?: string };
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? "Synchronisatie mislukt.");
      setMessage(`${payload.count ?? 0} apparaten gesynchroniseerd.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Synchronisatie mislukt.");
    } finally {
      setBusy(false);
    }
  }

  if (integration.mode !== "nest_sdm") {
    return <span className="status">Mobiele Home APIs</span>;
  }

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
      <a className="button" href="/api/google-home/oauth/start?mode=nest_sdm">
        Nest autoriseren
      </a>
      <button className="button" onClick={sync} disabled={busy}>
        {busy ? "Synchroniseren..." : "Synchroniseren"}
      </button>
      {message && <span className="status">{message}</span>}
    </div>
  );
}
