"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { IcsCalendarSubscription } from "@/lib/types";

export function IcsCalendarActions({ subscription }: { subscription: IcsCalendarSubscription }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const router = useRouter();

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch("/api/calendar-ics/sync", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: subscription.id }),
      });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; count?: number; error?: string };
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? "ICS synchronisatie mislukt.");
      setMessage(`${payload.count ?? 0} afspraken opgehaald.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ICS synchronisatie mislukt.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="integration-actions">
      <button className="button" type="button" onClick={sync} disabled={busy}>
        {busy ? "Ophalen..." : "Synchroniseren"}
      </button>
      {message && <span className="status">{message}</span>}
    </div>
  );
}
