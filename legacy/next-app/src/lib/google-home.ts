import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";

const SDM_SCOPE = "https://www.googleapis.com/auth/sdm.service";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
const SDM_API_BASE = "https://smartdevicemanagement.googleapis.com/v1";

type GoogleHomeMode = "home_apis" | "nest_sdm";

type GoogleHomeIntegrationRecord = {
  id: string;
  household_id: string;
  provider: "google_home";
  mode: GoogleHomeMode;
  status: "planned" | "needs_auth" | "configured" | "sync_error";
  project_id: string | null;
  client_id: string | null;
  client_secret: string | null;
  secret_refresh_token: string | null;
  access_token: string | null;
  expires_at: string | null;
};

type GoogleTokenResponse = {
  access_token?: string;
  expires_in?: number;
  refresh_token?: string;
  token_type?: string;
  error?: string;
  error_description?: string;
};

type SdmDevice = {
  name: string;
  type?: string;
  traits?: Record<string, unknown>;
  parentRelations?: Array<{ displayName?: string }>;
};

export function getNestSdmRedirectUri(origin: string) {
  return `${origin}/api/google-home/oauth/callback`;
}

export function buildNestSdmAuthorizationUrl(integration: GoogleHomeIntegrationRecord, origin: string, state: string) {
  if (!integration.project_id) throw new Error("Google Device Access project ID ontbreekt.");
  if (!integration.client_id) throw new Error("Google OAuth client ID ontbreekt.");

  const url = new URL(`https://nestservices.google.com/partnerconnections/${integration.project_id}/auth`);
  url.searchParams.set("redirect_uri", getNestSdmRedirectUri(origin));
  url.searchParams.set("client_id", integration.client_id);
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", SDM_SCOPE);
  url.searchParams.set("state", state);
  return url;
}

export async function getGoogleHomeIntegrationForCurrentUser(mode: string) {
  const auth = await requireLocalUser();
  if ("error" in auth) return { error: auth.error, status: auth.status };
  const { rows } = await query<GoogleHomeIntegrationRecord>(
    `select id, household_id, provider, mode, status, project_id, client_id, client_secret, secret_refresh_token, access_token, expires_at
     from smart_home_integrations
     where household_id = $1 and provider = 'google_home' and mode = $2`,
    [localIds.householdId, mode],
  );
  if (!rows[0]) return { error: "Google Home is nog niet gekoppeld.", status: 400 as const };
  return { integration: rows[0] };
}

export async function exchangeNestSdmCode(integration: GoogleHomeIntegrationRecord, origin: string, code: string) {
  if (!integration.client_id || !integration.client_secret) throw new Error("Google OAuth clientgegevens ontbreken.");

  const body = new URLSearchParams({
    code,
    client_id: integration.client_id,
    client_secret: integration.client_secret,
    redirect_uri: getNestSdmRedirectUri(origin),
    grant_type: "authorization_code",
  });

  return requestGoogleToken(body);
}

export async function getFreshNestSdmAccessToken(integration: GoogleHomeIntegrationRecord) {
  const expiresAt = integration.expires_at ? Date.parse(integration.expires_at) : 0;
  if (integration.access_token && expiresAt > Date.now() + 60_000) return integration.access_token;
  if (!integration.secret_refresh_token) throw new Error("Nest SDM is nog niet geautoriseerd.");
  if (!integration.client_id || !integration.client_secret) throw new Error("Google OAuth clientgegevens ontbreken.");

  const token = await requestGoogleToken(
    new URLSearchParams({
      client_id: integration.client_id,
      client_secret: integration.client_secret,
      refresh_token: integration.secret_refresh_token,
      grant_type: "refresh_token",
    }),
  );

  await persistGoogleToken(integration.id, token, integration.secret_refresh_token);
  if (!token.access_token) throw new Error("Google gaf geen access token terug.");
  return token.access_token;
}

export async function persistGoogleToken(integrationId: string, token: GoogleTokenResponse, existingRefreshToken?: string | null) {
  if (!token.access_token) throw new Error("Google gaf geen access token terug.");

  const expiresAt = new Date(Date.now() + Math.max((token.expires_in ?? 3600) - 60, 60) * 1000).toISOString();
  await query(
    `update smart_home_integrations
     set status = 'configured', access_token = $1, secret_refresh_token = $2, expires_at = $3
     where id = $4`,
    [token.access_token, token.refresh_token ?? existingRefreshToken ?? null, expiresAt, integrationId],
  );
}

export async function syncNestSdmDevices(integration: GoogleHomeIntegrationRecord) {
  if (!integration.project_id) throw new Error("Google Device Access project ID ontbreekt.");
  const accessToken = await getFreshNestSdmAccessToken(integration);

  const response = await fetch(`${SDM_API_BASE}/enterprises/${integration.project_id}/devices`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Nest SDM sync mislukt (${response.status}): ${message.slice(0, 220)}`);
  }

  const payload = (await response.json()) as { devices?: SdmDevice[] };
  const devices = payload.devices ?? [];
  for (const device of devices) {
    await query(
        `insert into smart_home_devices
          (household_id, integration_id, provider_device_id, name, type, room, traits, state, updated_at)
         values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, now())
         on conflict (integration_id, provider_device_id) do update set
           name = excluded.name,
           type = excluded.type,
           room = excluded.room,
           traits = excluded.traits,
           state = excluded.state,
           updated_at = now()`,
        [
          integration.household_id,
          integration.id,
          device.name,
          readableSdmDeviceName(device),
          device.type ?? null,
          device.parentRelations?.[0]?.displayName ?? null,
          JSON.stringify(device.traits ?? {}),
          JSON.stringify(flattenSdmState(device.traits ?? {})),
        ],
    );
  }
  await query("update smart_home_integrations set status = 'configured', last_sync_at = now() where id = $1", [integration.id]);
  return { count: devices.length };
}

async function requestGoogleToken(body: URLSearchParams) {
  const response = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  const token = (await response.json().catch(() => ({}))) as GoogleTokenResponse;
  if (!response.ok || token.error) {
    throw new Error(token.error_description || token.error || `Google token endpoint gaf status ${response.status}.`);
  }
  return token;
}

function readableSdmDeviceName(device: SdmDevice) {
  const info = device.traits?.["sdm.devices.traits.Info"];
  if (info && typeof info === "object" && "customName" in info && typeof info.customName === "string" && info.customName) {
    return info.customName;
  }
  return device.name.split("/").at(-1) ?? device.name;
}

function flattenSdmState(traits: Record<string, unknown>) {
  const state: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(traits)) {
    state[key.replace("sdm.devices.traits.", "")] = value;
  }
  return state;
}
