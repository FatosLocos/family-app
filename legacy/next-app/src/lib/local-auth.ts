import { cookies } from "next/headers";
import { randomBytes, randomUUID, scryptSync, timingSafeEqual, createHash } from "node:crypto";
import { localIds, query } from "@/lib/local-db";
import type { Profile } from "@/lib/types";

const sessionCookieName = "family_app_session";
const sessionDays = 30;

type LocalUserRow = Profile & {
  password_hash: string | null;
};

export async function getLocalUser() {
  const cookieStore = await cookies();
  const token = cookieStore.get(sessionCookieName)?.value;
  if (!token) return null;

  const tokenHash = hashToken(token);
  await query("update local_sessions set last_seen_at = now() where token_hash = $1 and expires_at > now()", [tokenHash]);
  const { rows } = await query<Profile>(
    `select p.id, p.full_name, p.email, p.phone, p.avatar_color, p.notification_email, p.digest_time
     from local_sessions s
     join profiles p on p.id = s.user_id
     join household_members hm on hm.user_id = p.id
     where s.token_hash = $1 and s.expires_at > now() and hm.household_id = $2`,
    [tokenHash, localIds.householdId],
  );

  return rows[0] ?? null;
}

export async function getLocalSessionOverviewForCurrentUser() {
  const cookieStore = await cookies();
  const token = cookieStore.get(sessionCookieName)?.value;
  const user = await getLocalUser();
  if (!user || !token) return null;
  const tokenHash = hashToken(token);
  const { rows } = await query<{
    id: string;
    created_at: string;
    last_seen_at: string;
    expires_at: string;
    is_current: boolean;
  }>(
    `select id, created_at, last_seen_at, expires_at, token_hash = $1 as is_current
     from local_sessions
     where user_id = $2 and expires_at > now()
     order by is_current desc, last_seen_at desc`,
    [tokenHash, user.id],
  );
  return rows;
}

export async function requireLocalUser() {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd.", status: 401 as const };
  return { user };
}

export async function createLocalAccount(input: { email: string; password: string; fullName?: string | null }) {
  const email = normalizeEmail(input.email);
  if (!email || input.password.length < 8) return { error: "Gebruik een geldig e-mailadres en minimaal 8 tekens." };

  const accountCount = await query<{ count: string }>("select count(*)::text as count from profiles where password_hash is not null");
  const hasAccounts = Number(accountCount.rows[0]?.count ?? "0") > 0;
  if (hasAccounts) {
    return { error: "Registratie is gesloten. Vraag de eigenaar om een uitnodiging." };
  }

  const existing = await query<LocalUserRow>("select id, full_name, email, password_hash from profiles where lower(email) = lower($1)", [email]);
  const passwordHash = hashPassword(input.password);

  if (existing.rows[0]?.password_hash) {
    return { error: "Er bestaat al een account met dit e-mailadres." };
  }

  const userId = existing.rows[0]?.id ?? localIds.userId;
  const role = "owner";

  await query(
    `insert into profiles (id, full_name, email, password_hash)
     values ($1, $2, $3, $4)
     on conflict (id) do update set
       full_name = excluded.full_name,
       email = excluded.email,
       password_hash = excluded.password_hash`,
    [userId, input.fullName || email.split("@")[0], email, passwordHash],
  );

  await query(
    `insert into household_members (household_id, user_id, role)
     values ($1, $2, $3)
     on conflict (household_id, user_id) do update set role = household_members.role`,
    [localIds.householdId, userId, role],
  );

  await createLocalSession(userId);
  return { ok: true };
}

export async function isLocalRegistrationOpen() {
  const accountCount = await query<{ count: string }>("select count(*)::text as count from profiles where password_hash is not null");
  return Number(accountCount.rows[0]?.count ?? "0") === 0;
}

export async function acceptLocalInvite(codeInput: string, input?: { email?: string | null; password?: string | null; fullName?: string | null }) {
  const code = normalizeInviteCode(codeInput);
  const invite = await getValidInvite(code);
  if (!invite) return { error: "Deze uitnodiging is ongeldig of verlopen." };

  const currentUser = await getLocalUser();
  if (currentUser) {
    await addLocalMemberAndAcceptInvite(invite.id, currentUser.id);
    return { ok: true };
  }

  const email = normalizeEmail(input?.email ?? "");
  const password = input?.password ?? "";
  if (!email || password.length < 8) return { error: "Vul een geldig e-mailadres en een wachtwoord van minimaal 8 tekens in." };

  const existing = await query<LocalUserRow>("select id, full_name, email, password_hash from profiles where lower(email) = lower($1)", [email]);
  const existingUser = existing.rows[0];

  if (existingUser?.password_hash) {
    if (!verifyPassword(password, existingUser.password_hash)) return { error: "Er bestaat al een account met dit e-mailadres. Log eerst in en open de invite-link opnieuw." };
    await createLocalSession(existingUser.id);
    await addLocalMemberAndAcceptInvite(invite.id, existingUser.id);
    return { ok: true };
  }

  const userId = existingUser?.id ?? randomUUID();
  await query(
    `insert into profiles (id, full_name, email, password_hash)
     values ($1, $2, $3, $4)
     on conflict (id) do update set
       full_name = excluded.full_name,
       email = excluded.email,
       password_hash = excluded.password_hash`,
    [userId, input?.fullName || email.split("@")[0], email, hashPassword(password)],
  );
  await addLocalMemberAndAcceptInvite(invite.id, userId);
  await createLocalSession(userId);
  return { ok: true };
}

export async function createLocalInviteForCurrentUser() {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd." };

  const role = await getLocalRole(user.id);
  if (role !== "owner" && role !== "admin") return { error: "Alleen de eigenaar kan uitnodigingen maken." };

  const code = randomBytes(5).toString("base64url").replace(/[^a-zA-Z0-9]/g, "").slice(0, 8).toUpperCase();
  const expiresAt = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString();
  await query(
    `insert into household_invites (household_id, code, invited_by, expires_at)
     values ($1, $2, $3, $4)`,
    [localIds.householdId, code, user.id, expiresAt],
  );
  return { ok: true };
}

export async function revokeLocalInviteForCurrentUser(inviteId: string) {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd." };
  const role = await getLocalRole(user.id);
  if (role !== "owner" && role !== "admin") return { error: "Alleen de eigenaar of beheerder kan uitnodigingen intrekken." };

  await query("delete from household_invites where id = $1 and household_id = $2 and accepted_at is null", [inviteId, localIds.householdId]);
  return { ok: true };
}

export async function updateLocalMemberRoleForCurrentUser(targetUserId: string, nextRole: string) {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd." };
  const currentRole = await getLocalRole(user.id);
  if (currentRole !== "owner") return { error: "Alleen de eigenaar kan rollen aanpassen." };
  if (targetUserId === user.id) return { error: "Je kunt je eigen rol niet aanpassen." };
  if (nextRole !== "admin" && nextRole !== "member") return { error: "Ongeldige rol." };

  const targetRole = await getLocalRole(targetUserId);
  if (!targetRole) return { error: "Gezinslid niet gevonden." };
  if (targetRole === "owner") return { error: "De eigenaar kan niet via deze actie worden aangepast." };

  await query("update household_members set role = $1 where household_id = $2 and user_id = $3", [nextRole, localIds.householdId, targetUserId]);
  return { ok: true };
}

export async function removeLocalMemberForCurrentUser(targetUserId: string) {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd." };
  const currentRole = await getLocalRole(user.id);
  if (currentRole !== "owner") return { error: "Alleen de eigenaar kan gezinsleden verwijderen." };
  if (targetUserId === user.id) return { error: "Je kunt jezelf niet verwijderen." };

  const targetRole = await getLocalRole(targetUserId);
  if (!targetRole) return { error: "Gezinslid niet gevonden." };
  if (targetRole === "owner") {
    const ownerCount = await query<{ count: string }>(
      "select count(*)::text as count from household_members where household_id = $1 and role = 'owner'",
      [localIds.householdId],
    );
    if (Number(ownerCount.rows[0]?.count ?? "0") <= 1) return { error: "Het huishouden moet minimaal één eigenaar houden." };
  }

  await query("delete from household_members where household_id = $1 and user_id = $2", [localIds.householdId, targetUserId]);
  await query("delete from local_sessions where user_id = $1", [targetUserId]);
  return { ok: true };
}

export async function updateLocalProfileForCurrentUser(input: {
  fullName?: string | null;
  email?: string | null;
  phone?: string | null;
  avatarColor?: string | null;
  notificationEmail?: boolean;
  digestTime?: string | null;
}) {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd." };
  const email = normalizeEmail(input.email ?? "");
  if (!email) return { error: "E-mail is verplicht." };

  const existing = await query<{ id: string }>("select id from profiles where lower(email) = lower($1) and id <> $2", [email, user.id]);
  if (existing.rows[0]) return { error: "Dit e-mailadres is al in gebruik." };

  await query(
    `update profiles
     set full_name = $1,
       email = $2,
       phone = $3,
       avatar_color = $4,
       notification_email = $5,
       digest_time = $6
     where id = $7`,
    [
      input.fullName || email.split("@")[0],
      email,
      input.phone || null,
      input.avatarColor || null,
      input.notificationEmail ?? true,
      input.digestTime || null,
      user.id,
    ],
  );
  return { ok: true };
}

export async function changeLocalPasswordForCurrentUser(currentPassword: string, nextPassword: string) {
  const user = await getLocalUser();
  if (!user) return { error: "Niet ingelogd." };
  if (nextPassword.length < 8) return { error: "Nieuw wachtwoord moet minimaal 8 tekens hebben." };

  const { rows } = await query<LocalUserRow>("select id, full_name, email, password_hash from profiles where id = $1", [user.id]);
  const current = rows[0];
  if (!current?.password_hash || !verifyPassword(currentPassword, current.password_hash)) return { error: "Huidig wachtwoord klopt niet." };

  await query("update profiles set password_hash = $1 where id = $2", [hashPassword(nextPassword), user.id]);
  await query("delete from local_sessions where user_id = $1", [user.id]);
  await createLocalSession(user.id);
  return { ok: true };
}

export async function revokeOtherLocalSessionsForCurrentUser() {
  const cookieStore = await cookies();
  const token = cookieStore.get(sessionCookieName)?.value;
  const user = await getLocalUser();
  if (!user || !token) return { error: "Niet ingelogd." };
  await query("delete from local_sessions where user_id = $1 and token_hash <> $2", [user.id, hashToken(token)]);
  return { ok: true };
}

export async function signInLocalAccount(emailInput: string, password: string) {
  const email = normalizeEmail(emailInput);
  const { rows } = await query<LocalUserRow>("select id, full_name, email, password_hash from profiles where lower(email) = lower($1)", [email]);
  const user = rows[0];

  if (!user?.password_hash || !verifyPassword(password, user.password_hash)) {
    return { error: "E-mailadres of wachtwoord klopt niet." };
  }

  await createLocalSession(user.id);
  return { ok: true };
}

export async function signOutLocalAccount() {
  const cookieStore = await cookies();
  const token = cookieStore.get(sessionCookieName)?.value;
  if (token) {
    await query("delete from local_sessions where token_hash = $1", [hashToken(token)]);
  }
  cookieStore.delete(sessionCookieName);
}

async function createLocalSession(userId: string) {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + sessionDays * 24 * 60 * 60 * 1000);
  await query("delete from local_sessions where expires_at <= now()");
  await query("insert into local_sessions (user_id, token_hash, expires_at) values ($1, $2, $3)", [userId, hashToken(token), expiresAt.toISOString()]);

  const cookieStore = await cookies();
  cookieStore.set(sessionCookieName, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: expiresAt,
  });
}

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

function normalizeInviteCode(code: string) {
  return code.trim().toUpperCase();
}

async function getValidInvite(code: string) {
  const { rows } = await query<{ id: string; household_id: string }>(
    `select id, household_id
     from household_invites
     where code = $1 and accepted_at is null and expires_at > now()`,
    [code],
  );
  return rows[0] ?? null;
}

async function getLocalRole(userId: string) {
  const { rows } = await query<{ role: string }>(
    "select role from household_members where household_id = $1 and user_id = $2",
    [localIds.householdId, userId],
  );
  return rows[0]?.role ?? null;
}

async function addLocalMemberAndAcceptInvite(inviteId: string, userId: string) {
  await query(
    `insert into household_members (household_id, user_id, role)
     values ($1, $2, 'member')
     on conflict (household_id, user_id) do nothing`,
    [localIds.householdId, userId],
  );
  await query("update household_invites set accepted_by = $1, accepted_at = now() where id = $2", [userId, inviteId]);
}

function hashPassword(password: string) {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, 64).toString("hex");
  return `scrypt:${salt}:${hash}`;
}

function verifyPassword(password: string, stored: string) {
  const [scheme, salt, hash] = stored.split(":");
  if (scheme !== "scrypt" || !salt || !hash) return false;
  const candidate = Buffer.from(scryptSync(password, salt, 64).toString("hex"), "hex");
  const expected = Buffer.from(hash, "hex");
  return candidate.length === expected.length && timingSafeEqual(candidate, expected);
}

function hashToken(token: string) {
  return createHash("sha256").update(token).digest("hex");
}
