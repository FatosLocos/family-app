"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Power, RefreshCw } from "lucide-react";
import type { HomeAssistantState } from "@/lib/types";

const supportedDomains = new Set(["light", "switch", "scene", "script", "cover", "climate", "media_player"]);

function domainOf(entityId: string) {
  return entityId.split(".")[0] ?? "";
}

function friendly(entity: HomeAssistantState) {
  return entity.attributes?.friendly_name ?? entity.entity_id;
}

export function HomeAssistantPanel({ configured }: { configured: boolean }) {
  const [entities, setEntities] = useState<HomeAssistantState[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadEntities = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    const response = await fetch("/api/home-assistant/states", { cache: "no-store" });
    const payload = (await response.json()) as { entities?: HomeAssistantState[]; error?: string };
    if (!response.ok) {
      setMessage(payload.error ?? "Home Assistant kon niet worden geladen.");
      setEntities([]);
    } else {
      setEntities(payload.entities ?? []);
    }
    setLoading(false);
  }, []);

  async function callService(entity: HomeAssistantState) {
    setMessage(null);
    const response = await fetch("/api/home-assistant/service", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entity_id: entity.entity_id }),
    });
    const payload = (await response.json()) as { error?: string };
    if (!response.ok) {
      setMessage(payload.error ?? "Actie mislukt.");
      return;
    }
    await loadEntities();
  }

  useEffect(() => {
    if (!configured) return;
    const timer = window.setTimeout(() => void loadEntities(), 0);
    return () => window.clearTimeout(timer);
  }, [configured, loadEntities]);

  const grouped = useMemo(() => {
    return entities.reduce<Record<string, HomeAssistantState[]>>((acc, entity) => {
      const domain = domainOf(entity.entity_id);
      acc[domain] = acc[domain] ?? [];
      acc[domain].push(entity);
      return acc;
    }, {});
  }, [entities]);

  if (!configured) {
    return <div className="card muted">Koppel Home Assistant eerst via Instellingen.</div>;
  }

  return (
    <section className="grid">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div>
          <h1 style={{ margin: 0 }}>Home</h1>
          <p className="muted">Bedien apparaten via Home Assistant.</p>
        </div>
        <button className="button" onClick={loadEntities} disabled={loading}>
          <RefreshCw size={17} /> Vernieuwen
        </button>
      </div>
      {message && <div className="error">{message}</div>}
      {Object.keys(grouped).length === 0 && <div className="card muted">Geen entiteiten gevonden.</div>}
      {Object.entries(grouped).map(([domain, items]) => (
        <div className="card" key={domain}>
          <h2>{domain}</h2>
          <ul className="list">
            {items.map((entity) => {
              const supported = supportedDomains.has(domain);
              return (
                <li className="list-row" key={entity.entity_id}>
                  <div className="row-main">
                    <div className="row-title">{friendly(entity)}</div>
                    <div className="row-meta">
                      {entity.entity_id} · {entity.state}
                    </div>
                  </div>
                  {supported ? (
                    <button className="icon-button" title="Bedienen" aria-label="Bedienen" onClick={() => callService(entity)}>
                      <Power size={17} />
                    </button>
                  ) : (
                    <span className="status">Alleen lezen</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}
