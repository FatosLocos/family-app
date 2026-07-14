import type { AppData } from "@/lib/types";
import { shortDate } from "@/lib/format";
import { GoogleHomeActions } from "@/components/google-home-actions";

export function GoogleHomePanel({ data }: { data: AppData }) {
  const integrations = data.smartHomeIntegrations.filter((integration) => integration.provider === "google_home");
  const googleDeviceIntegrationIds = new Set(integrations.map((integration) => integration.id));
  const devices = data.smartHomeDevices.filter((device) => googleDeviceIntegrationIds.has(device.integration_id));

  return (
    <div className="card">
      <h2>Google Home</h2>
      <ul className="list">
        {integrations.length === 0 && <li className="muted">Nog geen Google Home koppeling.</li>}
        {integrations.map((integration) => (
          <li className="list-row" key={integration.id}>
            <div>
              <div className="row-title">{integration.display_name}</div>
              <div className="row-meta">
                {integration.mode} · {integration.status} · laatst gesynchroniseerd {shortDate(integration.last_sync_at)}
              </div>
            </div>
            <GoogleHomeActions integration={integration} />
          </li>
        ))}
      </ul>
      {devices.length > 0 && (
        <>
          <h3 style={{ marginTop: 18 }}>Nest-apparaten</h3>
          <ul className="list">
            {devices.map((device) => (
              <li className="list-row" key={device.id}>
                <div>
                  <div className="row-title">{device.name}</div>
                  <div className="row-meta">
                    {device.room ?? "Geen ruimte"} · {device.type ?? "Onbekend type"} · {shortDate(device.updated_at)}
                  </div>
                </div>
                <span className="status">Alleen lezen</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted" style={{ marginBottom: 0 }}>
        Nest SDM synchroniseert ondersteunde Nest-apparaten via server-side OAuth. De bredere Google Home APIs blijven voorbereid voor een
        latere mobiele platformlaag.
      </p>
    </div>
  );
}
