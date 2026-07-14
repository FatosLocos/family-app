"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Power, RefreshCw } from "lucide-react";
import type { HueLight } from "@/lib/types";

export function HuePanel({ configured }: { configured: boolean }) {
  const [lights, setLights] = useState<HueLight[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadLights = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    const response = await fetch("/api/hue/lights", { cache: "no-store" });
    const payload = (await response.json()) as { lights?: HueLight[]; error?: string };
    if (!response.ok) {
      setMessage(payload.error ?? "Hue kon niet worden geladen.");
      setLights([]);
    } else {
      setLights(payload.lights ?? []);
    }
    setLoading(false);
  }, []);

  async function toggleLight(light: HueLight) {
    const response = await fetch(`/api/hue/lights/${light.rid}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: !light.on }),
    });
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    if (!response.ok) {
      setMessage(payload.error ?? "Hue actie mislukt.");
      return;
    }
    await loadLights();
  }

  useEffect(() => {
    if (!configured) return;
    const timer = window.setTimeout(() => void loadLights(), 0);
    return () => window.clearTimeout(timer);
  }, [configured, loadLights]);

  const activeCount = useMemo(() => lights.filter((light) => light.on).length, [lights]);

  if (!configured) {
    return <div className="card muted">Koppel Philips Hue eerst via Instellingen.</div>;
  }

  return (
    <section className="grid">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div>
          <h1 style={{ margin: 0 }}>Home</h1>
          <p className="muted">{activeCount} Hue lampen aan.</p>
        </div>
        <button className="button" onClick={loadLights} disabled={loading}>
          <RefreshCw size={17} /> Vernieuwen
        </button>
      </div>
      {message && <div className="error">{message}</div>}
      <div className="card">
        <h2>Philips Hue</h2>
        <ul className="list">
          {lights.length === 0 && <li className="muted">Geen Hue lampen gevonden.</li>}
          {lights.map((light) => (
            <li className="list-row" key={light.rid}>
              <div>
                <div className="row-title">{light.name}</div>
                <div className="row-meta">
                  {light.rid} · {light.on ? "aan" : "uit"} · {light.brightness === null ? "geen dimmer" : `${light.brightness}%`}
                </div>
              </div>
              <button className="button" onClick={() => toggleLight(light)}>
                <Power size={17} /> {light.on ? "Zet uit" : "Zet aan"}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
