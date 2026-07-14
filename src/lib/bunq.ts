import { randomUUID, sign as cryptoSign, generateKeyPairSync } from "node:crypto";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";

type BunqEnvironment = "sandbox" | "production";

type BunqConnectionRecord = {
  id: string;
  household_id: string;
  provider: "bunq";
  environment: BunqEnvironment;
  status: "configured" | "needs_session" | "sync_error";
  secret_api_key?: string | null;
  session_token?: string | null;
  oauth_client_id?: string | null;
  oauth_client_secret?: string | null;
  oauth_access_token?: string | null;
  oauth_token_type?: string | null;
  oauth_connected_at?: string | null;
};

type BunqOAuthTokenResponse = {
  access_token?: string;
  token_type?: string;
  state?: string;
  error?: string;
  error_description?: string;
};

type BunqSessionContext = {
  baseUrl: string;
  privateKey: string;
  sessionToken: string;
  userId: number;
  userIds: number[];
};

type BunqAccountSnapshot = {
  providerUserId: number;
  providerAccountId: string;
  name: string;
  iban: string | null;
  currency: string;
  balanceCents: number | null;
  raw: Record<string, unknown>;
};

type BunqPaymentSnapshot = {
  providerTransactionId: string;
  providerAccountId: string;
  bookedAt: string;
  description: string;
  counterparty: string | null;
  amountCents: number;
  currency: string;
  category: string | null;
  raw: Record<string, unknown>;
};

export function getBunqRedirectUri(origin: string) {
  return `${origin}/api/bunq/oauth/callback`;
}

export function buildBunqAuthorizationUrl(connection: BunqConnectionRecord, origin: string, state: string) {
  if (!connection.oauth_client_id) throw new Error("bunq OAuth client ID ontbreekt.");
  const url = new URL(connection.environment === "sandbox" ? "https://oauth.sandbox.bunq.com/auth" : "https://oauth.bunq.com/auth");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", connection.oauth_client_id);
  url.searchParams.set("redirect_uri", getBunqRedirectUri(origin));
  url.searchParams.set("state", state);
  return url;
}

export async function getBunqConnectionForCurrentUser() {
  if (hasLocalDatabaseEnv()) {
    const auth = await requireLocalUser();
    if ("error" in auth) return { error: auth.error, status: auth.status };
    const { rows } = await query<BunqConnectionRecord>(
      `select id, household_id, provider, environment, status, secret_api_key, session_token,
        oauth_client_id, oauth_client_secret, oauth_access_token, oauth_token_type, oauth_connected_at
       from bank_connections
       where household_id = $1 and provider = 'bunq'
       order by created_at desc
       limit 1`,
      [localIds.householdId],
    );
    if (!rows[0]) return { error: "bunq is nog niet gekoppeld.", status: 400 as const };
    return { connection: rows[0] };
  }

  return { error: "PostgreSQL is niet geconfigureerd.", status: 503 as const };
}

export async function exchangeBunqOAuthCode(connection: BunqConnectionRecord, origin: string, code: string) {
  if (!connection.oauth_client_id || !connection.oauth_client_secret) throw new Error("bunq OAuth clientgegevens ontbreken.");
  const tokenUrl = new URL(connection.environment === "sandbox" ? "https://api-oauth.sandbox.bunq.com/v1/token" : "https://api.oauth.bunq.com/v1/token");
  tokenUrl.searchParams.set("grant_type", "authorization_code");
  tokenUrl.searchParams.set("code", code);
  tokenUrl.searchParams.set("redirect_uri", getBunqRedirectUri(origin));
  tokenUrl.searchParams.set("client_id", connection.oauth_client_id);
  tokenUrl.searchParams.set("client_secret", connection.oauth_client_secret);
  const response = await fetch(tokenUrl, {
    method: "POST",
  });
  const payload = (await response.json().catch(() => ({}))) as BunqOAuthTokenResponse;
  if (!response.ok || payload.error) {
    throw new Error(payload.error_description ?? payload.error ?? "bunq OAuth token exchange mislukt.");
  }
  if (!payload.access_token) throw new Error("bunq gaf geen access token terug.");
  return payload;
}

export async function persistBunqOAuthToken(connectionId: string, token: BunqOAuthTokenResponse) {
  if (!token.access_token) throw new Error("bunq gaf geen access token terug.");
  if (hasLocalDatabaseEnv()) {
    await query(
      `update bank_connections
       set oauth_access_token = $1,
           oauth_token_type = $2,
           oauth_connected_at = now(),
           status = 'needs_session'
       where id = $3`,
      [token.access_token, token.token_type ?? "bearer", connectionId],
    );
    return;
  }
}

export async function syncBunqConnection(connection: BunqConnectionRecord) {
  const session = await createBunqSession(connection);
  const accounts = await fetchBunqAccounts(session);
  const payments = (
    await Promise.all(accounts.map((account) => fetchBunqPayments(session, account.providerUserId, account.providerAccountId)))
  ).flat();

  await persistBunqSnapshots(connection, session.sessionToken, accounts, payments);
  return { accountCount: accounts.length, transactionCount: payments.length };
}

export async function diagnoseBunqConnection(connection: BunqConnectionRecord) {
  const session = await createBunqSession(connection);
  const diagnostics = await inspectBunqAccountEndpoints(session);
  return {
    userIds: session.userIds,
    endpoints: diagnostics,
  };
}

async function createBunqSession(connection: BunqConnectionRecord): Promise<BunqSessionContext> {
  const secret = connection.oauth_access_token ?? connection.secret_api_key;
  if (!secret) throw new Error("bunq OAuth token of API key ontbreekt.");

  const baseUrl = bunqApiBaseUrl(connection.environment);
  const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    publicKeyEncoding: { type: "spki", format: "pem" },
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
  });

  const installation = await bunqRequest(`${baseUrl}/installation`, {
    method: "POST",
    body: { client_public_key: publicKey },
  });
  const installationToken = String(findBunqObject(installation, "Token")?.token ?? "");
  if (!installationToken) throw new Error("bunq installation gaf geen token terug.");

  await bunqRequest(`${baseUrl}/device-server`, {
    method: "POST",
    token: installationToken,
    privateKey,
    body: {
      description: "Family App",
      secret,
      permitted_ips: ["*"],
    },
  });

  const session = await bunqRequest(`${baseUrl}/session-server`, {
    method: "POST",
    token: installationToken,
    privateKey,
    body: { secret },
  });
  const sessionToken = String(findBunqObject(session, "Token")?.token ?? "");
  const userList = await bunqRequest(`${baseUrl}/user`, {
    method: "GET",
    token: sessionToken,
    privateKey,
  }).catch(() => null);
  const userIds = [...new Set([...getBunqSessionUserIds(session), ...(userList ? getBunqSessionUserIds(userList) : [])])];
  const userId = userIds[0] ?? null;
  if (!sessionToken || !userId) throw new Error("bunq sessie kon niet worden gemaakt.");

  return { baseUrl, privateKey, sessionToken, userId, userIds };
}

async function fetchBunqAccounts(session: BunqSessionContext) {
  const endpointResults = await inspectBunqAccountEndpoints(session);
  const accounts = endpointResults
    .flatMap((result) => result.accounts)
    .map(({ userId, account }) => parseBunqAccount(userId, account))
    .filter((account): account is BunqAccountSnapshot => Boolean(account));

  return [...new Map(accounts.map((account) => [`${account.providerUserId}:${account.providerAccountId}`, account])).values()];
}

async function inspectBunqAccountEndpoints(session: BunqSessionContext) {
  const endpoints = [
    "monetary-account",
    "monetary-account-bank",
    "monetary-account-savings",
    "monetary-account-savings-external",
    "monetary-account-joint",
    "monetary-account-external",
    "monetary-account-card",
  ];

  return (
    await Promise.all(
      session.userIds.flatMap((userId) =>
        endpoints.map(async (endpoint) => {
          try {
            const payload = await bunqRequest(`${session.baseUrl}/user/${userId}/${endpoint}?count=200`, {
              method: "GET",
              token: session.sessionToken,
              privateKey: session.privateKey,
            });
            const accounts = bunqResponseItems(payload)
              .map((item) =>
                unwrapBunqModel(item, [
                  "MonetaryAccountBank",
                  "MonetaryAccountSavings",
                  "MonetaryAccountExternalSavings",
                  "MonetaryAccountJoint",
                  "MonetaryAccountExternal",
                  "MonetaryAccountCard",
                ]),
              )
              .filter((account): account is Record<string, unknown> => Boolean(account));

            return {
              userId,
              endpoint,
              count: accounts.length,
              accounts: accounts.map((account) => ({ userId, account })),
              samples: accounts.slice(0, 5).map((account) => ({
                id: String(account.id ?? ""),
                name: String(account.description ?? account.display_name ?? "bunq rekening"),
                status: typeof account.status === "string" ? account.status : null,
              })),
            };
          } catch (error) {
            return {
              userId,
              endpoint,
              count: 0,
              accounts: [],
              samples: [],
              error: error instanceof Error ? bunqPublicError(error.message) : "endpoint niet beschikbaar",
            };
          }
        }),
      ),
    )
  ).filter((result) => result.count > 0 || result.error);
}

async function fetchBunqPayments(session: BunqSessionContext, userId: number, providerAccountId: string) {
  const payload = await bunqRequest(`${session.baseUrl}/user/${userId}/monetary-account/${providerAccountId}/payment?count=200`, {
    method: "GET",
    token: session.sessionToken,
    privateKey: session.privateKey,
  });
  return bunqResponseItems(payload)
    .map((item) => unwrapBunqModel(item, ["Payment"]))
    .filter(Boolean)
    .map((payment) => parseBunqPayment(providerAccountId, payment as Record<string, unknown>))
    .filter((payment): payment is BunqPaymentSnapshot => Boolean(payment));
}

function bunqPublicError(message: string) {
  return message
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]")
    .replace(/access_token=[^&\s]+/g, "access_token=[afgeschermd]")
    .replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]")
    .slice(0, 180);
}

async function persistBunqSnapshots(
  connection: BunqConnectionRecord,
  sessionToken: string,
  accounts: BunqAccountSnapshot[],
  payments: BunqPaymentSnapshot[],
) {
  if (hasLocalDatabaseEnv()) {
    const accountIdByProviderId = new Map<string, string>();
    for (const account of accounts) {
      const { rows } = await query<{ id: string }>(
        `insert into bank_accounts (household_id, connection_id, provider_account_id, name, iban, currency, balance_cents, updated_at)
         values ($1, $2, $3, $4, $5, $6, $7, now())
         on conflict (connection_id, provider_account_id) do update set
           name = excluded.name,
           iban = excluded.iban,
           currency = excluded.currency,
           balance_cents = excluded.balance_cents,
           updated_at = now()
         returning id`,
        [connection.household_id, connection.id, account.providerAccountId, account.name, account.iban, account.currency, account.balanceCents],
      );
      if (rows[0]?.id) accountIdByProviderId.set(account.providerAccountId, rows[0].id);
    }

    for (const payment of payments) {
      await query(
        `insert into bank_transactions
          (household_id, connection_id, account_id, provider_transaction_id, booked_at, description, counterparty, amount_cents, currency, category, raw)
         values ($1, $2, $3, $4, $5::timestamptz, $6, $7, $8, $9, $10, $11::jsonb)
         on conflict (connection_id, provider_transaction_id) do update set
           account_id = excluded.account_id,
           booked_at = excluded.booked_at,
           description = excluded.description,
           counterparty = excluded.counterparty,
           amount_cents = excluded.amount_cents,
           currency = excluded.currency,
           category = excluded.category,
           raw = excluded.raw`,
        [
          connection.household_id,
          connection.id,
          accountIdByProviderId.get(payment.providerAccountId) ?? null,
          payment.providerTransactionId,
          payment.bookedAt,
          payment.description,
          payment.counterparty,
          payment.amountCents,
          payment.currency,
          payment.category,
          JSON.stringify(payment.raw),
        ],
      );
    }

    await query("update bank_connections set status = 'configured', session_token = $1, last_sync_at = now() where id = $2", [sessionToken, connection.id]);
    return;
  }
}

async function bunqRequest(
  url: string,
  options: {
    method: "GET" | "POST";
    token?: string;
    privateKey?: string;
    body?: Record<string, unknown>;
  },
) {
  const body = options.body ? JSON.stringify(options.body) : "";
  const headers: Record<string, string> = {
    "Cache-Control": "no-cache",
    "User-Agent": "Family App",
    "X-Bunq-Language": "nl_NL",
    "X-Bunq-Region": "nl_NL",
    "X-Bunq-Geolocation": "0 0 0 0 NL",
    "X-Bunq-Client-Request-Id": randomUUID(),
  };
  if (options.body) headers["Content-Type"] = "application/json";
  if (options.token) headers["X-Bunq-Client-Authentication"] = options.token;
  if (options.privateKey) headers["X-Bunq-Client-Signature"] = signBunqBody(options.privateKey, body);

  const response = await fetch(url, { method: options.method, headers, body: options.body ? body : undefined });
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) throw new Error(bunqErrorMessage(payload, `bunq API call mislukt (${response.status}).`));
  return payload;
}

function signBunqBody(privateKey: string, body: string) {
  return cryptoSign("RSA-SHA256", Buffer.from(body), privateKey).toString("base64");
}

function bunqApiBaseUrl(environment: BunqEnvironment) {
  return environment === "sandbox" ? "https://public-api.sandbox.bunq.com/v1" : "https://api.bunq.com/v1";
}

function bunqResponseItems(payload: Record<string, unknown>) {
  return Array.isArray(payload.Response) ? (payload.Response as Array<Record<string, unknown>>) : [];
}

function findBunqObject(payload: Record<string, unknown>, key: string) {
  for (const item of bunqResponseItems(payload)) {
    const value = item[key];
    if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  }
  return null;
}

function unwrapBunqModel(item: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = item[key];
    if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  }
  return null;
}

function getBunqSessionUserIds(payload: Record<string, unknown>) {
  const ids = bunqResponseItems(payload)
    .flatMap((item) => ["UserPerson", "UserCompany", "UserApiKey"].map((key) => item[key]))
    .filter((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value))
    .map((user) => Number(user.id))
    .filter((id) => Number.isFinite(id));
  return [...new Set(ids)];
}

function parseBunqAccount(userId: number, account: Record<string, unknown>): BunqAccountSnapshot | null {
  const id = account.id;
  if (id === undefined || id === null) return null;
  const balance = account.balance && typeof account.balance === "object" ? (account.balance as Record<string, unknown>) : null;
  const aliases = Array.isArray(account.alias) ? (account.alias as Array<Record<string, unknown>>) : [];
  const iban = aliases.find((alias) => alias.type === "IBAN")?.value;
  return {
    providerUserId: userId,
    providerAccountId: String(id),
    name: String(account.description ?? account.display_name ?? "bunq rekening"),
    iban: typeof iban === "string" ? iban : null,
    currency: String(balance?.currency ?? "EUR"),
    balanceCents: amountToCents(balance?.value),
    raw: account,
  };
}

function parseBunqPayment(providerAccountId: string, payment: Record<string, unknown>): BunqPaymentSnapshot | null {
  const id = payment.id;
  if (id === undefined || id === null) return null;
  const amount = payment.amount && typeof payment.amount === "object" ? (payment.amount as Record<string, unknown>) : null;
  const counterpartyAlias = payment.counterparty_alias && typeof payment.counterparty_alias === "object" ? (payment.counterparty_alias as Record<string, unknown>) : null;
  const amountCents = amountToCents(amount?.value);
  if (amountCents === null) return null;
  const description = String(payment.description ?? "bunq transactie");
  const bookedAt = String(payment.created ?? payment.updated ?? new Date().toISOString());
  return {
    providerAccountId,
    providerTransactionId: `${providerAccountId}:${id}`,
    bookedAt,
    description,
    counterparty: counterpartyName(counterpartyAlias),
    amountCents,
    currency: String(amount?.currency ?? "EUR"),
    category: inferTransactionCategory(`${description} ${counterpartyName(counterpartyAlias) ?? ""}`),
    raw: payment,
  };
}

function amountToCents(value: unknown) {
  if (value === null || value === undefined) return null;
  const amount = Number(String(value).replace(",", "."));
  if (!Number.isFinite(amount)) return null;
  return Math.round(amount * 100);
}

function counterpartyName(alias: Record<string, unknown> | null) {
  if (!alias) return null;
  return String(alias.display_name ?? alias.name ?? alias.value ?? "") || null;
}

function inferTransactionCategory(value: string) {
  const normalized = value.toLowerCase();
  if (["albert heijn", "ah ", "jumbo", "lidl", "kaufland", "aldi", "plus", "dirk", "supermarkt"].some((store) => normalized.includes(store))) {
    return "Boodschappen";
  }
  return null;
}

function bunqErrorMessage(payload: Record<string, unknown>, fallback: string) {
  const errors = Array.isArray(payload.Error) ? (payload.Error as Array<Record<string, unknown>>) : [];
  const message = errors
    .map((error) => error.error_description ?? error.error_description_translated ?? error.error)
    .filter(Boolean)
    .join(" ");
  return sanitizeBunqError(message || fallback);
}

function sanitizeBunqError(message: string) {
  return message
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]")
    .replace(/access_token=[^&\s]+/g, "access_token=[afgeschermd]")
    .replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]");
}
