"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useFormStatus } from "react-dom";

export function BunqSubmitButton() {
  const { pending } = useFormStatus();

  return (
    <button className="button primary" disabled={pending}>
      {pending ? "bunq opslaan..." : "bunq opslaan"}
    </button>
  );
}

export function BunqSyncActions({ disabled = false }: { disabled?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<string[]>([]);

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch("/api/bunq/sync", { method: "POST" });
      const payload = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        accountCount?: number;
        transactionCount?: number;
        error?: string;
      };
      if (!response.ok || payload.error) throw new Error(payload.error ?? "bunq synchronisatie mislukt.");
      setMessage(`${payload.accountCount ?? 0} rekeningen en ${payload.transactionCount ?? 0} transacties gesynchroniseerd.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "bunq synchronisatie mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function diagnose() {
    setDiagnosing(true);
    setMessage(null);
    setDiagnostics([]);
    try {
      const response = await fetch("/api/bunq/diagnostics");
      const payload = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        userIds?: number[];
        endpoints?: Array<{
          userId: number;
          endpoint: string;
          count: number;
          samples?: Array<{ id: string; name: string; status: string | null }>;
          error?: string;
        }>;
        error?: string;
      };
      if (!response.ok || payload.error) throw new Error(payload.error ?? "bunq diagnose mislukt.");
      const lines = [
        `User-contexts: ${(payload.userIds ?? []).join(", ") || "geen"}`,
        ...(payload.endpoints ?? []).map((entry) => {
          const samples = (entry.samples ?? []).map((sample) => `${sample.name}${sample.status ? ` (${sample.status})` : ""}`).join(", ");
          return `user ${entry.userId} · ${entry.endpoint}: ${entry.count}${samples ? ` · ${samples}` : ""}${entry.error ? ` · ${entry.error}` : ""}`;
        }),
      ];
      setDiagnostics(lines);
      setMessage("bunq diagnose afgerond.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "bunq diagnose mislukt.");
    } finally {
      setDiagnosing(false);
    }
  }

  return (
    <div className="bunq-action-row">
      <button className="button" type="button" onClick={sync} disabled={disabled || busy}>
        {busy ? "Synchroniseren..." : "bunq synchroniseren"}
      </button>
      <button className="button ghost" type="button" onClick={diagnose} disabled={disabled || diagnosing}>
        {diagnosing ? "Diagnose..." : "diagnose"}
      </button>
      {message && <span className="status accent">{message}</span>}
      {diagnostics.length > 0 && (
        <ul className="bunq-diagnostics">
          {diagnostics.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
