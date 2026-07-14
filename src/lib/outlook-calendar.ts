import { hasLocalDatabaseEnv } from "@/lib/env";
import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";

const GRAPH_BASE = "https://graph.microsoft.com/v1.0";
const OUTLOOK_SCOPES = ["offline_access", "User.Read", "Calendars.Read"];

type OutlookIntegrationRecord = {
  id: string;
  household_id: string;
  user_id: string;
  provider: "outlook";
  status: "needs_auth" | "configured" | "sync_error";
  display_name: string;
  account_email: string | null;
  tenant_id: string;
  client_id: string;
  client_secret: string;
  secret_refresh_token: string | null;
  access_token: string | null;
  expires_at: string | null;
};

type MicrosoftTokenResponse = {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  error?: string;
  error_description?: string;
};

type OutlookAppConfig = {
  clientId: string;
  clientSecret: string;
  tenantId: string;
};

type StoredOutlookAppConfig = {
  client_id: string;
  client_secret: string;
  tenant_id: string;
};

type GraphEvent = {
  id: string;
  subject?: string;
  webLink?: string;
  isAllDay?: boolean;
  start?: { dateTime?: string; timeZone?: string };
  end?: { dateTime?: string; timeZone?: string };
  location?: { displayName?: string };
  organizer?: { emailAddress?: { name?: string; address?: string } };
};

type GraphCalendar = {
  id: string;
  name?: string;
  color?: string;
  canViewPrivateItems?: boolean;
};

export function getOutlookRedirectUri(origin: string) {
  return `${origin}/api/outlook-calendar/oauth/callback`;
}

export function buildOutlookAuthorizationUrl(integration: OutlookIntegrationRecord, origin: string, state: string, codeChallenge: string) {
  const tenant = integration.tenant_id || "consumers";
  const url = new URL(`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/authorize`);
  url.searchParams.set("client_id", integration.client_id);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("redirect_uri", getOutlookRedirectUri(origin));
  url.searchParams.set("response_mode", "query");
  url.searchParams.set("scope", OUTLOOK_SCOPES.join(" "));
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  return url;
}

export async function prepareOutlookIntegrationForCurrentUser() {
  if (!hasLocalDatabaseEnv()) return { error: "PostgreSQL is niet geconfigureerd.", status: 503 as const };

  const auth = await requireLocalUser();
  if ("error" in auth) return { error: auth.error, status: auth.status };

  const config = await getOutlookAppConfig(localIds.householdId);
  if ("error" in config) return config;

  const { rows } = await query<OutlookIntegrationRecord>(
    `insert into calendar_integrations
       (household_id, user_id, provider, status, display_name, tenant_id, client_id, client_secret)
     values ($1, $2, 'outlook', 'needs_auth', 'Outlook agenda', $3, $4, $5)
     on conflict (household_id, user_id, provider) do update set
       tenant_id = excluded.tenant_id,
       client_id = excluded.client_id,
       client_secret = excluded.client_secret
     returning id, household_id, user_id, provider, status, display_name, account_email, tenant_id, client_id, client_secret,
       secret_refresh_token, access_token, expires_at`,
    [localIds.householdId, auth.user.id, config.tenantId, config.clientId, config.clientSecret],
  );

  return { integration: rows[0] };
}

export async function getOutlookIntegrationForCurrentUser() {
  if (hasLocalDatabaseEnv()) {
    const auth = await requireLocalUser();
    if ("error" in auth) return { error: auth.error, status: auth.status };
    const { rows } = await query<OutlookIntegrationRecord>(
      `select id, household_id, user_id, provider, status, display_name, account_email, tenant_id, client_id, client_secret,
        secret_refresh_token, access_token, expires_at
       from calendar_integrations
       where household_id = $1 and user_id = $2 and provider = 'outlook'`,
      [localIds.householdId, localIds.userId],
    );
    if (!rows[0]) return { error: "Outlook agenda is nog niet gekoppeld.", status: 400 as const };
    return { integration: rows[0] };
  }

  return { error: "PostgreSQL is niet geconfigureerd.", status: 503 as const };
}

export async function exchangeOutlookCode(integration: OutlookIntegrationRecord, origin: string, code: string, codeVerifier: string) {
  return requestMicrosoftToken(
    integration,
    new URLSearchParams({
      client_id: integration.client_id,
      client_secret: integration.client_secret,
      code,
      code_verifier: codeVerifier,
      redirect_uri: getOutlookRedirectUri(origin),
      grant_type: "authorization_code",
    }),
  );
}

export async function persistOutlookToken(integrationId: string, token: MicrosoftTokenResponse, existingRefreshToken?: string | null) {
  if (!token.access_token) throw new Error("Microsoft gaf geen access token terug.");
  const expiresAt = new Date(Date.now() + Math.max((token.expires_in ?? 3600) - 60, 60) * 1000).toISOString();
  if (hasLocalDatabaseEnv()) {
    await query(
      `update calendar_integrations
       set status = 'configured', access_token = $1, secret_refresh_token = $2, expires_at = $3
       where id = $4`,
      [token.access_token, token.refresh_token ?? existingRefreshToken ?? null, expiresAt, integrationId],
    );
    return;
  }
}

export async function fetchOutlookAccountEmail(accessToken: string) {
  const response = await fetch(`${GRAPH_BASE}/me?$select=mail,userPrincipalName`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  const profile = (await response.json().catch(() => ({}))) as { mail?: string; userPrincipalName?: string };
  if (!response.ok) return null;
  return profile.mail ?? profile.userPrincipalName ?? null;
}

export async function saveOutlookAccountEmail(integrationId: string, accountEmail: string | null) {
  if (!hasLocalDatabaseEnv() || !accountEmail) return;
  await query("update calendar_integrations set account_email = $1 where id = $2", [accountEmail, integrationId]);
}

export async function syncOutlookCalendar(integration: OutlookIntegrationRecord) {
  const accessToken = await getFreshOutlookAccessToken(integration);
  const start = new Date();
  start.setDate(start.getDate() - 14);
  const end = new Date();
  end.setMonth(end.getMonth() + 3);

  const calendars = await fetchGraphCalendars(accessToken);
  const calendarEvents = await Promise.all(
    calendars.map(async (calendar) => {
      try {
        return {
          calendar,
          events: await fetchCalendarView(calendar.id, accessToken, start, end),
        };
      } catch {
        return { calendar, events: [] };
      }
    }),
  );
  const entries = calendarEvents.flatMap(({ calendar, events }) => events.map((event) => ({ calendar, event })));
  if (hasLocalDatabaseEnv()) {
    for (const { calendar, event } of entries) {
      await query(
        `insert into calendar_events
          (household_id, integration_id, external_event_id, external_calendar_id, external_calendar_name, source_provider,
           title, starts_at, ends_at, location, participant_ids, is_all_day, organizer_name, web_link, raw, updated_at)
         values ($1, $2, $3, $4, $5, 'outlook', $6, $7, $8, $9, $10::uuid[], $11, $12, $13, $14::jsonb, now())
         on conflict (integration_id, external_event_id) do update set
           external_calendar_id = excluded.external_calendar_id,
           external_calendar_name = excluded.external_calendar_name,
           title = excluded.title,
           starts_at = excluded.starts_at,
           ends_at = excluded.ends_at,
           location = excluded.location,
           participant_ids = excluded.participant_ids,
           is_all_day = excluded.is_all_day,
           organizer_name = excluded.organizer_name,
           web_link = excluded.web_link,
           raw = excluded.raw,
           updated_at = now()`,
        [
          integration.household_id,
          integration.id,
          `${calendar.id}:${event.id}`,
          calendar.id,
          calendar.name ?? "Outlook agenda",
          event.subject || "Outlook afspraak",
          graphDateTimeToIso(event.start),
          graphDateTimeToIso(event.end),
          event.location?.displayName || null,
          [integration.user_id],
          Boolean(event.isAllDay),
          event.organizer?.emailAddress?.name ?? event.organizer?.emailAddress?.address ?? null,
          event.webLink ?? null,
          JSON.stringify(event),
        ],
      );
    }
    await query("update calendar_integrations set status = 'configured', last_sync_at = now() where id = $1", [integration.id]);
    return { count: entries.length, calendarCount: calendars.length };
  }

  throw new Error("PostgreSQL is niet geconfigureerd.");
}

async function getFreshOutlookAccessToken(integration: OutlookIntegrationRecord) {
  const expiresAt = integration.expires_at ? Date.parse(integration.expires_at) : 0;
  if (integration.access_token && expiresAt > Date.now() + 60_000) return integration.access_token;
  if (!integration.secret_refresh_token) throw new Error("Outlook agenda is nog niet geautoriseerd.");

  const token = await requestMicrosoftToken(
    integration,
    new URLSearchParams({
      client_id: integration.client_id,
      client_secret: integration.client_secret,
      refresh_token: integration.secret_refresh_token,
      grant_type: "refresh_token",
    }),
  );
  await persistOutlookToken(integration.id, token, integration.secret_refresh_token);
  if (!token.access_token) throw new Error("Microsoft gaf geen access token terug.");
  return token.access_token;
}

async function requestMicrosoftToken(integration: OutlookIntegrationRecord, body: URLSearchParams) {
  const tenant = integration.tenant_id || "consumers";
  const response = await fetch(`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  const token = (await response.json().catch(() => ({}))) as MicrosoftTokenResponse;
  if (!response.ok || token.error) {
    throw new Error(token.error_description || token.error || `Microsoft token endpoint gaf status ${response.status}.`);
  }
  return token;
}

async function getOutlookAppConfig(householdId: string): Promise<OutlookAppConfig | { error: string; status: 503 }> {
  const stored = await query<StoredOutlookAppConfig>(
    "select client_id, client_secret, tenant_id from outlook_oauth_config where household_id = $1",
    [householdId],
  );
  const clientId = stored.rows[0]?.client_id?.trim() || process.env.OUTLOOK_CALENDAR_CLIENT_ID?.trim();
  const clientSecret = stored.rows[0]?.client_secret?.trim() || process.env.OUTLOOK_CALENDAR_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) {
    return {
      error: "Outlook is nog niet voorbereid. Vul eerst de Application (client) ID en client secret value in bij Instellingen.",
      status: 503,
    };
  }

  return {
    clientId,
    clientSecret,
    tenantId: stored.rows[0]?.tenant_id?.trim() || process.env.OUTLOOK_CALENDAR_TENANT_ID?.trim() || "consumers",
  };
}

async function fetchGraphEvents(url: URL, accessToken: string): Promise<GraphEvent[]> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Prefer: 'outlook.timezone="Europe/Amsterdam", IdType="ImmutableId"',
    },
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => ({}))) as { value?: GraphEvent[]; "@odata.nextLink"?: string; error?: { message?: string } };
  if (!response.ok) throw new Error(payload.error?.message || `Microsoft Graph gaf status ${response.status}.`);
  const events = payload.value ?? [];
  if (payload["@odata.nextLink"]) {
    return [...events, ...(await fetchGraphEvents(new URL(payload["@odata.nextLink"]), accessToken))];
  }
  return events;
}

async function fetchGraphCalendars(accessToken: string): Promise<GraphCalendar[]> {
  const url = new URL(`${GRAPH_BASE}/me/calendars`);
  url.searchParams.set("$select", "id,name,color,canViewPrivateItems");
  url.searchParams.set("$top", "100");
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Prefer: 'IdType="ImmutableId"',
    },
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => ({}))) as { value?: GraphCalendar[]; error?: { message?: string } };
  if (!response.ok) throw new Error(payload.error?.message || `Microsoft Graph agenda's ophalen gaf status ${response.status}.`);
  const calendars = payload.value ?? [];
  return calendars.length > 0 ? calendars : [{ id: "calendar", name: "Outlook agenda" }];
}

function fetchCalendarView(calendarId: string, accessToken: string, start: Date, end: Date) {
  const url = new URL(`${GRAPH_BASE}/me/calendars/${encodeURIComponent(calendarId)}/calendarView`);
  url.searchParams.set("startDateTime", start.toISOString());
  url.searchParams.set("endDateTime", end.toISOString());
  url.searchParams.set("$select", "id,subject,start,end,location,organizer,webLink,isAllDay");
  url.searchParams.set("$orderby", "start/dateTime");
  url.searchParams.set("$top", "100");
  return fetchGraphEvents(url, accessToken);
}

function graphDateTimeToIso(value?: { dateTime?: string; timeZone?: string }) {
  if (!value?.dateTime) return new Date().toISOString();
  const normalized = value.dateTime.endsWith("Z") ? value.dateTime : `${value.dateTime}Z`;
  return new Date(normalized).toISOString();
}
