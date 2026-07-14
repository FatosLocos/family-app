"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { fetchFreeShoppingPrices } from "@/lib/checkjebon-price-provider";
import { fetchKauflandPrices } from "@/lib/kaufland-provider";
import { fetchPrijsProfeetOffers } from "@/lib/prijsprofeet-provider";
import { parseAbnAmroStatement, parseAbnAmroWorkbook } from "@/lib/abn-amro-import";
import { centsFromEuros, centsFromText, formValue as value, internalRedirectPath } from "@/lib/form-utils";
import { normalizeHouseholdPreferencesInput } from "@/lib/household-preferences";
import { parseIcsEvents, upsertIcsCalendarEvents } from "@/lib/ics-calendar";
import { parseAddressBookFile } from "@/lib/address-book";
import { recurringTransactionRuleIdentity } from "@/lib/finance-insights";
import { getShoppingPriceProviderStatus, hasLocalDatabaseEnv } from "@/lib/env";
import { localIds, query } from "@/lib/local-db";
import { buildStarterPack } from "@/lib/starter-pack";
import {
  acceptLocalInvite,
  changeLocalPasswordForCurrentUser,
  createLocalAccount,
  createLocalInviteForCurrentUser,
  getLocalUser,
  removeLocalMemberForCurrentUser,
  revokeOtherLocalSessionsForCurrentUser,
  revokeLocalInviteForCurrentUser,
  signInLocalAccount,
  signOutLocalAccount,
  updateLocalProfileForCurrentUser,
  updateLocalMemberRoleForCurrentUser,
} from "@/lib/local-auth";
import type { ShoppingItem } from "@/lib/types";

export async function signIn(formData: FormData) {
  const email = value(formData, "email");
  const password = value(formData, "password");
  const next = internalRedirectPath(value(formData, "next"));
  if (!email || !password) return redirect("/login?error=Vul je e-mail en wachtwoord in.");

  if (hasLocalDatabaseEnv()) {
    const result = await signInLocalAccount(email, password);
    if (result.error) return redirect(`/login?error=${encodeURIComponent(result.error)}`);
    redirect(next);
  }
}

export async function signUp(formData: FormData) {
  const email = value(formData, "email");
  const password = value(formData, "password");
  const fullName = value(formData, "full_name");
  if (!email || !password) return redirect("/login?error=Vul je e-mail en wachtwoord in.");

  if (hasLocalDatabaseEnv()) {
    const result = await createLocalAccount({ email, password, fullName });
    if (result.error) return redirect(`/login?error=${encodeURIComponent(result.error)}`);
    redirect("/");
  }
}

export async function signOut() {
  if (hasLocalDatabaseEnv()) {
    await signOutLocalAccount();
    redirect("/login");
  }
}

export async function openInviteCode(formData: FormData) {
  const code = value(formData, "invite_code")?.trim();
  if (!code) redirect("/login?error=Vul een uitnodigingscode in.");
  redirect(`/invite/${encodeURIComponent(code.toUpperCase())}`);
}

export async function createHousehold(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  const name = value(formData, "name") ?? "Ons gezin";
  const preferences = normalizeHouseholdPreferencesInput({
    week_starts_on: value(formData, "week_starts_on"),
    default_dashboard: value(formData, "default_dashboard"),
    default_shopping_store: value(formData, "default_shopping_store"),
    quiet_hours_start: value(formData, "quiet_hours_start") ?? "22:00",
    quiet_hours_end: value(formData, "quiet_hours_end") ?? "07:00",
  });
  await ensureLocalActionUser();
  await query("update households set name = $1 where id = $2", [name, localIds.householdId]);
  await query(
    `insert into household_preferences (
       household_id, week_starts_on, default_dashboard, default_shopping_store, quiet_hours_start, quiet_hours_end, updated_at
     ) values ($1, $2, $3, $4, $5, $6, now())
     on conflict (household_id) do update set
       week_starts_on = excluded.week_starts_on,
       default_dashboard = excluded.default_dashboard,
       default_shopping_store = excluded.default_shopping_store,
       quiet_hours_start = excluded.quiet_hours_start,
       quiet_hours_end = excluded.quiet_hours_end,
       updated_at = now()`,
    [
      localIds.householdId,
      preferences.week_starts_on,
      preferences.default_dashboard,
      preferences.default_shopping_store,
      preferences.quiet_hours_start,
      preferences.quiet_hours_end,
    ],
  );
  revalidatePath("/");
  redirect("/");
}

export async function addHouseholdContact(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const name = value(formData, "name");
  if (!name) return;
  await query(
    `insert into household_contacts (household_id, name, relationship, phone, email, address, notes, priority)
     values ($1, $2, $3, $4, $5, $6, $7, $8)`,
    [
      localIds.householdId,
      name,
      value(formData, "relationship"),
      value(formData, "phone"),
      value(formData, "email"),
      value(formData, "address"),
      value(formData, "notes"),
      normalizeContactPriority(value(formData, "priority")),
    ],
  );
  revalidateCorePaths();
}

export async function deleteHouseholdContact(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query(
    `delete from household_birthdays
     where household_id = $1
       and contact_member_id in (select id from household_contact_members where household_id = $1 and contact_id = $2)`,
    [localIds.householdId, id],
  );
  await query("delete from household_contacts where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function addAddressBookContact(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const name = value(formData, "name");
  if (!name) throw new Error("Vul een naam of familienaam in.");
  await query(
    `insert into household_contacts (
       household_id, name, contact_type, relationship, phone, email, address, postal_code, city, country, notes, priority
     ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)`,
    [
      localIds.householdId,
      name,
      normalizeContactType(value(formData, "contact_type")),
      value(formData, "relationship"),
      value(formData, "phone"),
      value(formData, "email"),
      value(formData, "address"),
      value(formData, "postal_code"),
      value(formData, "city"),
      value(formData, "country"),
      value(formData, "notes"),
      normalizeContactPriority(value(formData, "priority")),
    ],
  );
  revalidateCorePaths();
}

export async function addAddressBookMember(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const contactId = value(formData, "contact_id");
  const name = value(formData, "name");
  if (!contactId || !name) throw new Error("Kies een contact en vul een naam in.");
  const birthDate = validBirthDate(value(formData, "birth_date"));
  const result = await query<{ id: string }>(
    `insert into household_contact_members (household_id, contact_id, name, relationship, birth_date, phone, email, notes)
     select $1, id, $3, $4, $5, $6, $7, $8
     from household_contacts where id = $2 and household_id = $1
     on conflict (contact_id, name, birth_date) do update set
       relationship = excluded.relationship, phone = excluded.phone, email = excluded.email, notes = excluded.notes
     returning id`,
    [
      localIds.householdId,
      contactId,
      name,
      value(formData, "relationship"),
      birthDate,
      value(formData, "phone"),
      value(formData, "email"),
      value(formData, "notes"),
    ],
  );
  const memberId = result.rows[0]?.id;
  if (!memberId) throw new Error("Dit contact bestaat niet meer.");
  if (birthDate) {
    await query(
      `insert into household_birthdays (household_id, name, birth_date, relation, notes, contact_member_id)
       values ($1, $2, $3, $4, $5, $6)
       on conflict (household_id, name, birth_date) do update set
         relation = excluded.relation, notes = excluded.notes, contact_member_id = excluded.contact_member_id`,
      [localIds.householdId, name, birthDate, value(formData, "relationship"), value(formData, "notes"), memberId],
    );
  }
  revalidateCorePaths();
}

export async function deleteAddressBookMember(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from household_birthdays where household_id = $1 and contact_member_id = $2", [localIds.householdId, id]);
  await query("delete from household_contact_members where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function importAddressBookContacts(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const file = formData.get("contacts_file");
  if (!(file instanceof File) || file.size === 0) throw new Error("Kies een CSV- of vCard-bestand.");
  if (file.size > 2_000_000) throw new Error("Het contactbestand is groter dan 2 MB.");
  const contacts = parseAddressBookFile(await file.text(), file.name).slice(0, 500);
  if (contacts.length === 0) throw new Error("Geen herkenbare contacten gevonden in dit bestand.");

  let imported = 0;
  for (const contact of contacts) {
    const existing = await query<{ id: string }>(
      "select id from household_contacts where household_id = $1 and lower(name) = lower($2) limit 1",
      [localIds.householdId, contact.name],
    );
    const contactId = existing.rows[0]?.id ?? (await query<{ id: string }>(
      `insert into household_contacts (household_id, name, contact_type, relationship, phone, email, address, postal_code, city, country, notes, priority)
       values ($1, $2, 'persoon', $3, $4, $5, $6, $7, $8, $9, $10, 'normaal') returning id`,
      [localIds.householdId, contact.name, contact.relationship ?? null, contact.phone ?? null, contact.email ?? null, contact.address ?? null, contact.postalCode ?? null, contact.city ?? null, contact.country ?? null, contact.notes ?? null],
    )).rows[0]?.id;
    if (!contactId) continue;
    imported += 1;
    if (contact.birthDate) {
      const member = await query<{ id: string }>(
        `insert into household_contact_members (household_id, contact_id, name, birth_date)
         values ($1, $2, $3, $4)
         on conflict (contact_id, name, birth_date) do update set name = excluded.name
         returning id`,
        [localIds.householdId, contactId, contact.name, contact.birthDate],
      );
      const memberId = member.rows[0]?.id;
      if (memberId) {
        await query(
          `insert into household_birthdays (household_id, name, birth_date, relation, contact_member_id)
           values ($1, $2, $3, $4, $5)
           on conflict (household_id, name, birth_date) do update set contact_member_id = excluded.contact_member_id`,
          [localIds.householdId, contact.name, contact.birthDate, contact.relationship ?? null, memberId],
        );
      }
    }
  }
  revalidateCorePaths();
  redirect(`/adresboek?imported=${imported}`);
}

export async function addHouseholdBirthday(formData: FormData) {
  const name = value(formData, "name");
  const birthDate = value(formData, "birth_date");
  if (!name || !birthDate || !/^\d{4}-\d{2}-\d{2}$/.test(birthDate)) throw new Error("Vul een naam en geldige geboortedatum in.");
  const relation = value(formData, "relation");
  const memberId = value(formData, "member_id") || null;
  const notes = value(formData, "notes");

  if (hasLocalDatabaseEnv()) {
    await ensureLocalActionUser();
    await query(
      `insert into household_birthdays (household_id, name, birth_date, relation, member_id, notes)
       values ($1, $2, $3, $4, $5, $6)
       on conflict (household_id, name, birth_date) do update set relation = excluded.relation, member_id = excluded.member_id, notes = excluded.notes`,
      [localIds.householdId, name, birthDate, relation, memberId, notes],
    );
    revalidatePath("/agenda");
    return;
  }
}

export async function deleteHouseholdBirthday(formData: FormData) {
  const id = value(formData, "id");
  if (!id) return;
  if (hasLocalDatabaseEnv()) {
    await ensureLocalActionUser();
    await query("delete from household_birthdays where id = $1 and household_id = $2", [id, localIds.householdId]);
    revalidatePath("/agenda");
    return;
  }
}

export async function addHouseholdInfoItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const title = value(formData, "title");
  if (!title) return;
  await query(
    `insert into household_info_items (household_id, title, category, value, notes, is_sensitive)
     values ($1, $2, $3, $4, $5, $6)`,
    [
      localIds.householdId,
      title,
      value(formData, "category") ?? "Algemeen",
      value(formData, "value"),
      value(formData, "notes"),
      value(formData, "is_sensitive") === "on",
    ],
  );
  revalidateCorePaths();
}

export async function deleteHouseholdInfoItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from household_info_items where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function addMaintenanceItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const title = value(formData, "title");
  if (!title) return;
  await query(
    `insert into maintenance_items (household_id, title, area, provider, due_date, frequency, notes)
     values ($1, $2, $3, $4, nullif($5, '')::date, $6, $7)`,
    [
      localIds.householdId,
      title,
      value(formData, "area"),
      value(formData, "provider"),
      value(formData, "due_date"),
      normalizeMaintenanceFrequency(value(formData, "frequency")),
      value(formData, "notes"),
    ],
  );
  revalidateCorePaths();
}

export async function completeMaintenanceItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  const result = await query<{
    title: string;
    area: string | null;
    provider: string | null;
    due_date: string | null;
    frequency: string;
    notes: string | null;
  }>("select title, area, provider, due_date, frequency, notes from maintenance_items where id = $1 and household_id = $2", [id, localIds.householdId]);
  const item = result.rows[0];
  if (!item) return;
  await query("update maintenance_items set status = 'done', completed_at = now() where id = $1 and household_id = $2", [id, localIds.householdId]);
  const nextDueDate = nextMaintenanceDate(item.due_date, item.frequency);
  if (nextDueDate) {
    await query(
      `insert into maintenance_items (household_id, title, area, provider, due_date, frequency, notes)
       values ($1, $2, $3, $4, $5::date, $6, $7)`,
      [localIds.householdId, item.title, item.area, item.provider, nextDueDate, item.frequency, item.notes],
    );
  }
  revalidateCorePaths();
}

export async function deleteMaintenanceItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from maintenance_items where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function addHouseholdNote(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  const user = await ensureLocalActionUser();
  const title = value(formData, "title");
  const body = value(formData, "body");
  if (!title || !body) return;
  await query(
    `insert into household_notes (household_id, title, body, category, pinned, expires_at, created_by)
     values ($1, $2, $3, $4, $5, nullif($6, '')::date, $7)`,
    [
      localIds.householdId,
      title,
      body,
      value(formData, "category") ?? "Algemeen",
      value(formData, "pinned") === "on",
      value(formData, "expires_at"),
      user.id,
    ],
  );
  revalidateCorePaths();
}

export async function toggleHouseholdNotePin(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  const pinned = value(formData, "pinned") !== "true";
  if (!id) return;
  await query("update household_notes set pinned = $1 where id = $2 and household_id = $3", [pinned, id, localIds.householdId]);
  revalidateCorePaths();
}

export async function deleteHouseholdNote(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from household_notes where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function addHouseholdDocument(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const title = value(formData, "title");
  if (!title) return;
  await query(
    `insert into household_documents (household_id, title, category, owner_name, location, reference, expires_at, notes, is_sensitive)
     values ($1, $2, $3, $4, $5, $6, nullif($7, '')::date, $8, $9)`,
    [
      localIds.householdId,
      title,
      value(formData, "category") ?? "Algemeen",
      value(formData, "owner_name"),
      value(formData, "location"),
      value(formData, "reference"),
      value(formData, "expires_at"),
      value(formData, "notes"),
      value(formData, "is_sensitive") === "on",
    ],
  );
  revalidateCorePaths();
}

export async function deleteHouseholdDocument(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from household_documents where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function addWishlistItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const title = value(formData, "title");
  if (!title) return;
  const priceCents = centsFromEuros(value(formData, "price")) ?? centsFromText(value(formData, "price") ?? "");
  const purchaseMode = normalizeWishlistPurchaseMode(value(formData, "purchase_mode"));
  await query(
    `insert into wishlist_items (household_id, title, description, url, image_url, desired_by, category, price_cents, priority, purchase_mode, is_public)
     values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
    [
      localIds.householdId,
      title,
      value(formData, "description"),
      normalizeOptionalUrl(value(formData, "url")),
      normalizeOptionalUrl(value(formData, "image_url")),
      value(formData, "desired_by"),
      value(formData, "category") ?? "Algemeen",
      priceCents,
      normalizeWishlistPriority(value(formData, "priority")),
      purchaseMode,
      value(formData, "is_public") === "on",
    ],
  );
  revalidateCorePaths();
}

export async function deleteWishlistItem(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from wishlist_items where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function toggleWishlistItemPublic(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  const isPublic = value(formData, "is_public") !== "true";
  await query("update wishlist_items set is_public = $1, updated_at = now() where id = $2 and household_id = $3", [isPublic, id, localIds.householdId]);
  revalidateCorePaths();
}

export async function setWishlistItemStatus(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  const status = normalizeWishlistStatus(value(formData, "status"));
  if (!id) return;
  await query(
    `update wishlist_items
     set status = case when purchase_mode = 'repeatable' and $1 = 'purchased' then 'open' else $1 end,
         reserved_by_name = case when $1 = 'open' or (purchase_mode = 'repeatable' and $1 = 'purchased') then null else reserved_by_name end,
         reserved_at = case when $1 = 'open' or (purchase_mode = 'repeatable' and $1 = 'purchased') then null when $1 = 'reserved' and reserved_at is null then now() else reserved_at end,
         purchased_at = case when purchase_mode = 'repeatable' then null when $1 = 'purchased' then now() else null end,
         last_purchased_at = case when $1 = 'purchased' then now() else last_purchased_at end,
         purchase_count = case when $1 = 'purchased' then coalesce(purchase_count, 0) + 1 else purchase_count end,
         updated_at = now()
     where id = $2 and household_id = $3`,
    [status, id, localIds.householdId],
  );
  revalidateCorePaths();
}

export async function ensureWishlistShare() {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  await query(
    `insert into wishlist_shares (household_id, title, public_token, enabled)
     values ($1, 'Verlanglijst Ons gezin', $2, true)
     on conflict (household_id) do update set enabled = true, updated_at = now()`,
    [localIds.householdId, crypto.randomUUID().replace(/-/g, "").slice(0, 24)],
  );
  revalidateCorePaths();
}

export async function toggleWishlistShare(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  const enabled = value(formData, "enabled") !== "true";
  await query("update wishlist_shares set enabled = $1, updated_at = now() where id = $2 and household_id = $3", [enabled, id, localIds.householdId]);
  revalidateCorePaths();
}

export async function reservePublicWishlistItem(formData: FormData) {
  const token = value(formData, "token");
  const id = value(formData, "id");
  const name = value(formData, "name");
  if (!hasLocalDatabaseEnv() || !token || !id || !name) return;
  const result = await query<{ id: string }>(
    `update wishlist_items wi
     set status = 'reserved',
         reserved_by_name = $3,
         reserved_at = now(),
         purchased_at = null,
         updated_at = now()
     from wishlist_shares ws
     where wi.id = $1
       and wi.household_id = ws.household_id
       and ws.public_token = $2
       and ws.enabled = true
       and wi.is_public = true
       and wi.status = 'open'
     returning wi.id`,
    [id, token, name.slice(0, 80)],
  );
  if (result.rows[0]) revalidatePath(`/wishlist/${token}`);
}

export async function purchasePublicWishlistItem(formData: FormData) {
  const token = value(formData, "token");
  const id = value(formData, "id");
  const name = value(formData, "name");
  if (!hasLocalDatabaseEnv() || !token || !id) return;
  const result = await query<{ id: string }>(
    `update wishlist_items wi
     set status = case when wi.purchase_mode = 'repeatable' then 'open' else 'purchased' end,
         reserved_by_name = case when wi.purchase_mode = 'repeatable' then null else coalesce(nullif($3, ''), reserved_by_name) end,
         reserved_at = case when wi.purchase_mode = 'repeatable' then null else coalesce(reserved_at, now()) end,
         purchased_at = case when wi.purchase_mode = 'repeatable' then null else now() end,
         last_purchased_at = now(),
         purchase_count = coalesce(wi.purchase_count, 0) + 1,
         updated_at = now()
     from wishlist_shares ws
     where wi.id = $1
       and wi.household_id = ws.household_id
       and ws.public_token = $2
       and ws.enabled = true
       and wi.is_public = true
       and wi.status in ('open', 'reserved')
     returning wi.id`,
    [id, token, name?.slice(0, 80) ?? null],
  );
  if (result.rows[0]) revalidatePath(`/wishlist/${token}`);
}

export async function createInvite() {
  if (hasLocalDatabaseEnv()) {
    const result = await createLocalInviteForCurrentUser();
    if (result.error) throw new Error(result.error);
    revalidatePath("/instellingen");
    return;
  }
}

export async function acceptInvite(code: string, formData?: FormData) {
  if (hasLocalDatabaseEnv()) {
    const result = await acceptLocalInvite(code, {
      email: formData ? value(formData, "email") : null,
      password: formData ? value(formData, "password") : null,
      fullName: formData ? value(formData, "full_name") : null,
    });
    if (result.error) redirect(`/invite/${code}?error=${encodeURIComponent(result.error)}`);
    redirect("/");
  }
}

export async function revokeInvite(formData: FormData) {
  const id = value(formData, "id");
  if (!id) return;
  if (hasLocalDatabaseEnv()) {
    const result = await revokeLocalInviteForCurrentUser(id);
    if (result.error) throw new Error(result.error);
    revalidatePath("/instellingen");
    return;
  }
}

export async function updateMemberRole(formData: FormData) {
  const userId = value(formData, "user_id");
  const role = value(formData, "role");
  if (!userId || !role) return;
  if (hasLocalDatabaseEnv()) {
    const result = await updateLocalMemberRoleForCurrentUser(userId, role);
    if (result.error) throw new Error(result.error);
    revalidatePath("/instellingen");
    return;
  }
}

export async function removeMember(formData: FormData) {
  const userId = value(formData, "user_id");
  if (!userId) return;
  if (hasLocalDatabaseEnv()) {
    const result = await removeLocalMemberForCurrentUser(userId);
    if (result.error) throw new Error(result.error);
    revalidatePath("/instellingen");
    return;
  }
}

export async function updateProfile(formData: FormData) {
  if (hasLocalDatabaseEnv()) {
    const result = await updateLocalProfileForCurrentUser({
      fullName: value(formData, "full_name"),
      email: value(formData, "email"),
      phone: value(formData, "phone"),
      avatarColor: value(formData, "avatar_color"),
      notificationEmail: value(formData, "notification_email") === "on",
      digestTime: value(formData, "digest_time"),
    });
    if (result.error) throw new Error(result.error);
    revalidatePath("/");
    revalidatePath("/instellingen");
    return;
  }
}

export async function updateHouseholdPreferences(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const preferences = normalizeHouseholdPreferencesInput({
    week_starts_on: value(formData, "week_starts_on"),
    default_dashboard: value(formData, "default_dashboard"),
    default_shopping_store: value(formData, "default_shopping_store"),
    quiet_hours_start: value(formData, "quiet_hours_start"),
    quiet_hours_end: value(formData, "quiet_hours_end"),
  });
  await query(
    `insert into household_preferences (
       household_id,
       week_starts_on,
       default_dashboard,
       default_shopping_store,
       quiet_hours_start,
       quiet_hours_end,
       updated_at
     )
     values ($1, $2, $3, $4, $5, $6, now())
     on conflict (household_id) do update set
       week_starts_on = excluded.week_starts_on,
       default_dashboard = excluded.default_dashboard,
       default_shopping_store = excluded.default_shopping_store,
       quiet_hours_start = excluded.quiet_hours_start,
       quiet_hours_end = excluded.quiet_hours_end,
       updated_at = now()`,
    [
      localIds.householdId,
      preferences.week_starts_on,
      preferences.default_dashboard,
      preferences.default_shopping_store,
      preferences.quiet_hours_start,
      preferences.quiet_hours_end,
    ],
  );
  revalidateCorePaths();
  revalidatePath("/instellingen");
}

export async function changePassword(formData: FormData) {
  const currentPassword = value(formData, "current_password");
  const nextPassword = value(formData, "next_password");
  if (!currentPassword || !nextPassword) return;
  if (hasLocalDatabaseEnv()) {
    const result = await changeLocalPasswordForCurrentUser(currentPassword, nextPassword);
    if (result.error) throw new Error(result.error);
    revalidatePath("/instellingen");
    return;
  }
}

export async function revokeOtherSessions() {
  if (hasLocalDatabaseEnv()) {
    const result = await revokeOtherLocalSessionsForCurrentUser();
    if (result.error) throw new Error(result.error);
    revalidatePath("/instellingen");
  }
}

export async function applyStarterPack() {
  if (!hasLocalDatabaseEnv()) return;
  const user = await ensureLocalActionUser();
  const pack = buildStarterPack();

  for (const contact of pack.contacts) {
    await query(
      `insert into household_contacts (household_id, name, relationship, priority, notes)
       select $1, $2, $3, $4, $5
       where not exists (
         select 1 from household_contacts where household_id = $1 and lower(name) = lower($2)
       )`,
      [localIds.householdId, contact.name, contact.relationship, contact.priority, contact.notes],
    );
  }

  for (const item of pack.householdInfoItems) {
    await query(
      `insert into household_info_items (household_id, title, category, value, notes, is_sensitive)
       select $1, $2, $3, $4, $5, false
       where not exists (
         select 1 from household_info_items where household_id = $1 and lower(title) = lower($2)
       )`,
      [localIds.householdId, item.title, item.category, item.value, item.notes],
    );
  }

  for (const task of pack.tasks) {
    await query(
      `insert into tasks (household_id, title, description, priority, due_date, recurrence)
       select $1, $2, $3, $4, $5::date, $6
       where not exists (
         select 1 from tasks where household_id = $1 and lower(title) = lower($2) and parent_task_id is null
       )`,
      [localIds.householdId, task.title, task.description, task.priority, task.due_date, task.recurrence],
    );
  }

  for (const product of pack.shoppingProducts) {
    const result = await query<{ id: string }>(
      `insert into shopping_products (household_id, name, category, default_quantity, recurrence)
       values ($1, $2, $3, $4, $5)
       on conflict (household_id, name) do update set
         category = coalesce(shopping_products.category, excluded.category),
         default_quantity = coalesce(shopping_products.default_quantity, excluded.default_quantity),
         recurrence = case when shopping_products.recurrence = 'none' then excluded.recurrence else shopping_products.recurrence end
       returning id`,
      [localIds.householdId, product.name, product.category, product.default_quantity, product.recurrence],
    );
    await query(
      `insert into shopping_items (household_id, list_id, product_id, name, quantity, category)
       select $1, $2, $3, $4, $5, $6
       where not exists (
         select 1 from shopping_items where household_id = $1 and lower(name) = lower($4) and checked = false
       )`,
      [localIds.householdId, localIds.listId, result.rows[0]?.id, product.name, product.default_quantity, product.category],
    );
  }

  for (const budget of pack.financeBudgets) {
    await query(
      `insert into finance_budgets (household_id, category, monthly_limit_cents, alert_threshold)
       values ($1, $2, $3, $4)
       on conflict (household_id, category) do nothing`,
      [localIds.householdId, budget.category, budget.monthly_limit_cents, budget.alert_threshold],
    );
  }

  for (const item of pack.financeItems) {
    await query(
      `insert into finance_items (household_id, title, category, amount_cents, frequency, due_date, status)
       select $1, $2, $3, $4, $5, $6::date, $7
       where not exists (
         select 1 from finance_items where household_id = $1 and lower(title) = lower($2)
       )`,
      [localIds.householdId, item.title, item.category, item.amount_cents, item.frequency, item.due_date, item.status],
    );
  }

  for (const item of pack.maintenanceItems) {
    await query(
      `insert into maintenance_items (household_id, title, area, provider, due_date, frequency, notes)
       select $1, $2, $3, $4, $5::date, $6, $7
       where not exists (
         select 1 from maintenance_items where household_id = $1 and lower(title) = lower($2)
       )`,
      [localIds.householdId, item.title, item.area, item.provider, item.due_date, item.frequency, item.notes],
    );
  }

  for (const document of pack.documents) {
    await query(
      `insert into household_documents (household_id, title, category, location, notes, is_sensitive)
       select $1, $2, $3, $4, $5, false
       where not exists (
         select 1 from household_documents where household_id = $1 and lower(title) = lower($2)
       )`,
      [localIds.householdId, document.title, document.category, document.location, document.notes],
    );
  }

  for (const note of pack.notes) {
    await query(
      `insert into household_notes (household_id, title, body, category, pinned, expires_at, created_by)
       select $1, $2, $3, $4, $5, $6::date, $7
       where not exists (
         select 1 from household_notes where household_id = $1 and lower(title) = lower($2)
       )`,
      [localIds.householdId, note.title, note.body, note.category, note.pinned, note.expires_at, user.id],
    );
  }

  for (const meal of pack.mealPlans) {
    await query(
      `insert into meal_plans (household_id, planned_date, meal_type, title, notes, ingredients)
       select $1, $2::date, $3, $4, $5, $6
       where not exists (
         select 1 from meal_plans where household_id = $1 and lower(title) = lower($4)
       )`,
      [localIds.householdId, meal.planned_date, meal.meal_type, meal.title, meal.notes, meal.ingredients],
    );
  }

  revalidateCorePaths();
  redirect("/inrichting?starter=toegevoegd");
}

export async function addTask(formData: FormData) {
  if (hasLocalDatabaseEnv()) return addLocalTask(formData);}

export async function quickAdd(formData: FormData) {
  const kind = value(formData, "kind") ?? "task";
  const title = value(formData, "title");
  if (!title) return;

  if (hasLocalDatabaseEnv()) {
    const user = await ensureLocalActionUser();
    const details = value(formData, "details");
    const category = value(formData, "category");

    if (kind === "shopping") {
      const product = await query<{ id: string }>(
        `insert into shopping_products (household_id, name, category, default_quantity, recurrence)
         values ($1, $2, $3, $4, 'none')
         on conflict (household_id, name) do update set
           category = coalesce(excluded.category, shopping_products.category),
           default_quantity = coalesce(excluded.default_quantity, shopping_products.default_quantity)
         returning id`,
        [localIds.householdId, title, category || "Snel toegevoegd", details],
      );
      await query(
        "insert into shopping_items (household_id, list_id, product_id, name, quantity, category) values ($1, $2, $3, $4, $5, $6)",
        [localIds.householdId, localIds.listId, product.rows[0]?.id, title, details, category || "Snel toegevoegd"],
      );
      revalidateCorePaths();
      redirect("/boodschappen");
    }

    if (kind === "note") {
      await query(
        `insert into household_notes (household_id, title, body, category, pinned, expires_at, created_by)
         values ($1, $2, $3, $4, $5, nullif($6, '')::date, $7)`,
        [
          localIds.householdId,
          title,
          details || title,
          category || "Snel toegevoegd",
          formData.get("pinned") === "on",
          value(formData, "expires_at"),
          user.id,
        ],
      );
      revalidateCorePaths();
      redirect("/prikbord");
    }

    if (kind === "event") {
      await query(
        `insert into calendar_events (household_id, title, starts_at, location, participant_ids)
         values ($1, $2, $3::timestamptz, $4, '{}')`,
        [localIds.householdId, title, quickDateTime(value(formData, "due_date")), details],
      );
      revalidateCorePaths();
      redirect("/agenda");
    }

    if (kind === "meal") {
      await query(
        `insert into meal_plans (household_id, planned_date, meal_type, title, notes, ingredients)
         values ($1, nullif($2, '')::date, 'avondeten', $3, $4, $5)`,
        [localIds.householdId, value(formData, "due_date") ?? new Date().toISOString().slice(0, 10), title, category, details],
      );
      revalidateCorePaths();
      redirect("/boodschappen?tab=maaltijden");
    }

    if (kind === "finance") {
      const amountCents = centsFromEuros(details) ?? centsFromText(`${title} ${details ?? ""}`);
      if (amountCents === null) redirect("/snel?error=Zet een bedrag in de titel of details, bijvoorbeeld schoolfoto 12,50.");
      await query(
        `insert into finance_items (household_id, title, category, amount_cents, frequency, due_date, status)
         values ($1, $2, $3, $4, 'eenmalig', nullif($5, '')::date, 'actief')`,
        [localIds.householdId, title, category || "Snel toegevoegd", amountCents, value(formData, "due_date")],
      );
      revalidateCorePaths();
      redirect("/geld");
    }

    await query(
      `insert into tasks (household_id, title, description, priority, due_date)
       values ($1, $2, $3, $4, nullif($5, '')::date)`,
      [localIds.householdId, title, details, value(formData, "priority") ?? "normaal", value(formData, "due_date")],
    );
    revalidateCorePaths();
    redirect("/taken");
  }
}

export async function toggleTask(formData: FormData) {
  if (hasLocalDatabaseEnv()) return toggleLocalTask(formData);}

export async function addSubtask(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const parentTaskId = value(formData, "parent_task_id");
  const title = value(formData, "title");
  if (!parentTaskId || !title) return;
  const parentResult = await query<{ assignee_id: string | null; priority: string; due_date: string | null }>(
    "select assignee_id, priority, due_date from tasks where id = $1 and household_id = $2",
    [parentTaskId, localIds.householdId],
  );
  const parent = parentResult.rows[0];
  if (!parent) return;
  await query(
    `insert into tasks (household_id, title, assignee_id, priority, due_date, parent_task_id)
     values ($1, $2, $3, $4, $5, $6)`,
    [localIds.householdId, title, parent.assignee_id, parent.priority, parent.due_date, parentTaskId],
  );
  revalidateCorePaths();
}

export async function deleteTask(formData: FormData) {
  if (hasLocalDatabaseEnv()) return deleteLocalTask(formData);}

export async function addShoppingItem(formData: FormData) {
  if (hasLocalDatabaseEnv()) return addLocalShoppingItem(formData);}

export async function toggleShoppingItem(formData: FormData) {
  if (hasLocalDatabaseEnv()) return toggleLocalShoppingItem(formData);}

export async function deleteShoppingItem(formData: FormData) {
  if (hasLocalDatabaseEnv()) return deleteLocalShoppingItem(formData);}

export async function clearCheckedShoppingItems() {
  if (hasLocalDatabaseEnv()) return clearLocalCheckedShoppingItems();}

export async function addRecurringProductToShopping(formData: FormData) {
  if (hasLocalDatabaseEnv()) return addLocalRecurringProductToShopping(formData);}

export async function addMealPlan(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const title = value(formData, "title");
  const plannedDate = value(formData, "planned_date");
  if (!title || !plannedDate) return;
  await query(
    `insert into meal_plans (household_id, planned_date, meal_type, title, notes, ingredients)
     values ($1, nullif($2, '')::date, $3, $4, $5, $6)`,
    [
      localIds.householdId,
      plannedDate,
      normalizeMealType(value(formData, "meal_type")),
      title,
      value(formData, "notes"),
      value(formData, "ingredients"),
    ],
  );
  revalidateCorePaths();
}

export async function deleteMealPlan(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from meal_plans where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function addMealIngredientsToShopping(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  const mealResult = await query<{ ingredients: string | null }>("select ingredients from meal_plans where id = $1 and household_id = $2", [
    id,
    localIds.householdId,
  ]);
  const ingredients = parseIngredients(mealResult.rows[0]?.ingredients ?? "");
  for (const ingredient of ingredients) {
    const product = await query<{ id: string }>(
      `insert into shopping_products (household_id, name, category, recurrence)
       values ($1, $2, 'Maaltijden', 'none')
       on conflict (household_id, name) do update set category = coalesce(shopping_products.category, excluded.category)
       returning id`,
      [localIds.householdId, ingredient],
    );
    await query(
      `insert into shopping_items (household_id, list_id, product_id, name, category)
       select $1, $2, $3, $4, 'Maaltijden'
       where not exists (
         select 1 from shopping_items
         where household_id = $1 and lower(name) = lower($4) and checked = false
       )`,
      [localIds.householdId, localIds.listId, product.rows[0]?.id, ingredient],
    );
  }
  revalidateCorePaths();
}

export async function addWeekMealIngredientsToShopping() {
  if (hasLocalDatabaseEnv()) return addLocalWeekMealIngredientsToShopping();}

async function addLocalWeekMealIngredientsToShopping() {
  await ensureLocalActionUser();
  const today = new Date().toISOString().slice(0, 10);
  const nextWeek = addDays(today, 7);
  const meals = await query<{ ingredients: string | null }>(
    "select ingredients from meal_plans where household_id = $1 and planned_date >= $2::date and planned_date <= $3::date",
    [localIds.householdId, today, nextWeek],
  );
  const ingredients = uniqueParsedIngredients(meals.rows.flatMap((meal) => parseIngredients(meal.ingredients ?? "")));
  for (const ingredient of ingredients) {
    const product = await query<{ id: string }>(
      `insert into shopping_products (household_id, name, category, recurrence)
       values ($1, $2, 'Maaltijden', 'none')
       on conflict (household_id, name) do update set category = coalesce(shopping_products.category, excluded.category)
       returning id`,
      [localIds.householdId, ingredient],
    );
    await query(
      `insert into shopping_items (household_id, list_id, product_id, name, category)
       select $1, $2, $3, $4, 'Maaltijden'
       where not exists (
         select 1 from shopping_items
         where household_id = $1 and lower(name) = lower($4) and checked = false
       )`,
      [localIds.householdId, localIds.listId, product.rows[0]?.id, ingredient],
    );
  }
  revalidateCorePaths();
}

export async function addFinanceItem(formData: FormData) {
  if (hasLocalDatabaseEnv()) return addLocalFinanceItem(formData);}

export async function addFinanceBudget(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const category = value(formData, "category");
  const monthlyLimitCents = centsFromEuros(value(formData, "monthly_limit"));
  const threshold = Number(value(formData, "alert_threshold") ?? "80") / 100;
  if (!category || monthlyLimitCents === null) return;
  await query(
    `insert into finance_budgets (household_id, category, monthly_limit_cents, alert_threshold, updated_at)
     values ($1, $2, $3, $4, now())
     on conflict (household_id, category) do update set
       monthly_limit_cents = excluded.monthly_limit_cents,
       alert_threshold = excluded.alert_threshold,
       updated_at = now()`,
    [localIds.householdId, category, monthlyLimitCents, Number.isFinite(threshold) ? threshold : 0.8],
  );
  revalidateCorePaths();
}

export async function deleteFinanceBudget(formData: FormData) {
  if (!hasLocalDatabaseEnv()) return;
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from finance_budgets where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

export async function deleteFinanceItem(formData: FormData) {
  if (hasLocalDatabaseEnv()) return deleteLocalFinanceItem(formData);}

export async function markFinanceItemPaid(formData: FormData) {
  if (hasLocalDatabaseEnv()) return markLocalFinanceItemPaid(formData);}

export async function addCalendarEvent(formData: FormData) {
  if (hasLocalDatabaseEnv()) return addLocalCalendarEvent(formData);}

export async function deleteCalendarEvent(formData: FormData) {
  if (hasLocalDatabaseEnv()) return deleteLocalCalendarEvent(formData);}

export async function saveHomeAssistantConfig(formData: FormData) {
  if (hasLocalDatabaseEnv()) return saveLocalHomeAssistantConfig(formData);}

export async function saveHueConfig(formData: FormData) {
  if (hasLocalDatabaseEnv()) return saveLocalHueConfig(formData);}

export async function saveGoogleHomeIntegration(formData: FormData) {
  if (hasLocalDatabaseEnv()) return saveLocalGoogleHomeIntegration(formData);}

export async function saveOutlookOAuthConfig(formData: FormData) {
  if (hasLocalDatabaseEnv()) return saveLocalOutlookOAuthConfig(formData);}

export async function saveIcsCalendarSubscription(formData: FormData) {
  const displayName = value(formData, "display_name") || "ICS agenda";
  const feedUrl = normalizeOptionalUrl(value(formData, "feed_url"));
  if (!feedUrl) throw new Error("Vul een geldige http(s) ICS-link in.");

  if (hasLocalDatabaseEnv()) {
    const user = await ensureLocalActionUser();
    await query(
      `insert into ics_calendar_subscriptions (household_id, user_id, display_name, feed_url, status)
       values ($1, $2, $3, $4, 'configured')
       on conflict (household_id, user_id, feed_url) do update set display_name = excluded.display_name, status = 'configured', updated_at = now()`,
      [localIds.householdId, user.id, displayName, feedUrl],
    );
    revalidatePath("/agenda");
    return;
  }
}

export async function importIcsCalendarFile(formData: FormData) {
  const displayName = value(formData, "display_name") || "Geimporteerde ICS agenda";
  const file = formData.get("ics_file");
  if (!(file instanceof File) || file.size === 0) throw new Error("Kies een geldig ICS-bestand.");
  if (file.size > 2_000_000) throw new Error("Het ICS-bestand is groter dan 2 MB.");
  if (!file.name.toLowerCase().endsWith(".ics") && file.type !== "text/calendar") {
    throw new Error("Alleen .ics-agendabestanden worden ondersteund.");
  }

  const content = await file.text();
  if (!/BEGIN:VCALENDAR/i.test(content)) throw new Error("Dit bestand is geen geldig ICS-agendabestand.");
  const events = parseIcsEvents(content);
  if (events.length === 0) throw new Error("Geen afspraken gevonden in dit ICS-bestand.");

  if (hasLocalDatabaseEnv()) {
    const user = await ensureLocalActionUser();
    const result = await query<{ id: string }>(
      `insert into ics_calendar_file_imports (household_id, user_id, display_name, file_name, status, last_imported_at)
       values ($1, $2, $3, $4, 'configured', now())
       on conflict (household_id, user_id, display_name) do update set
         file_name = excluded.file_name, status = 'configured', last_imported_at = now(), updated_at = now()
       returning id`,
      [localIds.householdId, user.id, displayName, file.name],
    );
    const id = result.rows[0]?.id;
    if (!id) throw new Error("ICS-bestand kon niet worden opgeslagen.");
    await upsertIcsCalendarEvents({ id, household_id: localIds.householdId, user_id: user.id, display_name: displayName }, events);
    revalidatePath("/agenda");
    return;
  }
}

export async function deleteIcsCalendarSource(formData: FormData) {
  const id = value(formData, "id");
  const kind = value(formData, "kind");
  if (!id || (kind !== "subscription" && kind !== "file")) return;
  const table = kind === "file" ? "ics_calendar_file_imports" : "ics_calendar_subscriptions";

  if (hasLocalDatabaseEnv()) {
    const user = await ensureLocalActionUser();
    const source = await query<{ id: string }>(
      `select id from ${table} where id = $1 and household_id = $2 and user_id = $3`,
      [id, localIds.householdId, user.id],
    );
    if (!source.rows[0]) throw new Error("Deze agenda-koppeling kan niet worden verwijderd.");
    await query(`delete from ${table} where id = $1 and household_id = $2 and user_id = $3`, [id, localIds.householdId, user.id]);
    await query("delete from calendar_events where household_id = $1 and integration_id = $2", [localIds.householdId, id]);
    revalidatePath("/agenda");
    return;
  }
}

export async function saveBunqConnection(formData: FormData) {
  if (hasLocalDatabaseEnv()) return saveLocalBunqConnection(formData);}

export async function importAbnAmroStatement(formData: FormData) {
  const file = formData.get("statement_file");
  if (!(file instanceof File) || file.size === 0) throw new Error("Kies een ABN AMRO exportbestand.");
  if (file.size > 2_000_000) throw new Error("Het bestand is te groot. Gebruik een CSV- of Excel-export tot 2 MB.");
  const buffer = await file.arrayBuffer();
  const fallbackName = value(formData, "account_name") || "ABN AMRO import";
  const fileName = file.name.toLowerCase();
  const isExcel = fileName.endsWith(".xls") || fileName.endsWith(".xlsx") || file.type.includes("spreadsheet") || file.type.includes("excel");
  const statement = isExcel ? parseAbnAmroWorkbook(buffer, fallbackName) : parseAbnAmroStatement(new TextDecoder("utf-8").decode(buffer), fallbackName);
  if (statement.transactions.length === 0) throw new Error("Geen transacties herkend in dit ABN AMRO bestand.");

  if (hasLocalDatabaseEnv()) {
    await ensureLocalActionUser();
    const connection = await query<{ id: string }>(
      `insert into bank_connections (household_id, provider, environment, status, last_sync_at)
       values ($1, 'abn_amro_manual', 'production', 'configured', now())
       on conflict (household_id, provider) do update set status = 'configured', last_sync_at = now()
       returning id`,
      [localIds.householdId],
    );
    const connectionId = connection.rows[0]?.id;
    if (!connectionId) throw new Error("ABN AMRO import kon geen bankkoppeling maken.");
    const account = await query<{ id: string }>(
      `insert into bank_accounts (household_id, connection_id, provider_account_id, name, iban, currency, updated_at)
       values ($1, $2, $3, $4, $5, 'EUR', now())
       on conflict (connection_id, provider_account_id) do update set
         name = excluded.name,
         iban = excluded.iban,
         updated_at = now()
       returning id`,
      [localIds.householdId, connectionId, statement.accountIdentifier, statement.accountName, statement.iban],
    );
    const accountId = account.rows[0]?.id ?? null;
    for (const transaction of statement.transactions) {
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
          localIds.householdId,
          connectionId,
          accountId,
          transaction.providerTransactionId,
          transaction.bookedAt,
          transaction.description,
          transaction.counterparty,
          transaction.amountCents,
          transaction.currency,
          inferManualTransactionCategory(`${transaction.description} ${transaction.counterparty ?? ""}`),
          JSON.stringify({ provider: "abn_amro_manual", filename: file.name, ...transaction.raw }),
        ],
      );
    }
    revalidatePath("/geld");
    redirect(`/geld?imported=${statement.transactions.length}&skipped=${statement.skippedRows}`);
  }
}

export async function setRecurringTransactionRule(formData: FormData) {
  const transactionId = value(formData, "transaction_id");
  const action = value(formData, "rule_action");
  const directRuleKey = value(formData, "rule_key");
  const directLabel = value(formData, "label");
  if (action !== "force_recurring" && action !== "exclude_recurring") return;

  if (hasLocalDatabaseEnv()) {
    await ensureLocalActionUser();
    let ruleKey = directRuleKey;
    let label = directLabel;
    if (!ruleKey || !label) {
      if (!transactionId) return;
      const transaction = await query<{ description: string }>(
        "select description from bank_transactions where id = $1 and household_id = $2",
        [transactionId, localIds.householdId],
      );
      const description = transaction.rows[0]?.description;
      if (!description) return;
      const identity = recurringTransactionRuleIdentity(description);
      ruleKey = identity.ruleKey;
      label = identity.label;
    }
    await query(
      `insert into recurring_transaction_rules (household_id, rule_key, label, action, updated_at)
       values ($1, $2, $3, $4, now())
       on conflict (household_id, rule_key) do update set
         label = excluded.label,
         action = excluded.action,
         updated_at = now()`,
      [localIds.householdId, ruleKey, label, action],
    );
    revalidatePath("/geld");
    return;
  }
}

export async function setRecurringTransactionGroup(formData: FormData) {
  const ruleKey = value(formData, "rule_key");
  const label = value(formData, "label");
  const groupId = value(formData, "group_id");
  if (!ruleKey || !label || !isRecurringGroupId(groupId)) return;

  if (hasLocalDatabaseEnv()) {
    await ensureLocalActionUser();
    await query(
      `insert into recurring_transaction_rules (household_id, rule_key, label, action, group_id, updated_at)
       values ($1, $2, $3, 'group_recurring', $4, now())
       on conflict (household_id, rule_key) do update set
         label = excluded.label,
         group_id = excluded.group_id,
         action = case
           when recurring_transaction_rules.action = 'force_recurring' then 'force_recurring'
           else 'group_recurring'
         end,
         updated_at = now()`,
      [localIds.householdId, ruleKey, label, groupId],
    );
    revalidatePath("/geld");
    return;
  }
}

function isRecurringGroupId(groupId: string | null): groupId is string {
  return typeof groupId === "string" && ["fixed", "insurance", "credit", "subscription", "tax", "other"].includes(groupId);
}

export async function saveTaskIntegration(formData: FormData) {
  if (hasLocalDatabaseEnv()) return saveLocalTaskIntegration(formData);}

async function addLocalTask(formData: FormData) {
  await ensureLocalActionUser();
  const title = value(formData, "title");
  if (!title) return;
  const recurrence = normalizeTaskRecurrence(value(formData, "recurrence"));
  await query(
    `insert into tasks (household_id, title, description, assignee_id, priority, due_date, recurrence)
     values ($1, $2, $3, nullif($4, '')::uuid, $5, nullif($6, '')::date, $7)`,
    [
      localIds.householdId,
      title,
      value(formData, "description"),
      value(formData, "assignee_id"),
      value(formData, "priority") ?? "normaal",
      value(formData, "due_date"),
      recurrence,
    ],
  );
  revalidateCorePaths();
}

async function saveLocalHomeAssistantConfig(formData: FormData) {
  await ensureLocalActionUser();
  const baseUrl = value(formData, "base_url");
  const token = value(formData, "token");
  if (!baseUrl || !token) throw new Error("Home Assistant URL en token zijn verplicht.");
  await query(
    `insert into home_assistant_config (household_id, base_url, token, updated_at)
     values ($1, $2, $3, now())
     on conflict (household_id) do update set base_url = excluded.base_url, token = excluded.token, updated_at = now()`,
    [localIds.householdId, baseUrl.replace(/\/$/, ""), token],
  );
  revalidatePath("/home");
  revalidatePath("/instellingen");
}

async function saveLocalHueConfig(formData: FormData) {
  await ensureLocalActionUser();
  const bridgeUrl = value(formData, "bridge_url");
  const appKey = value(formData, "app_key");
  if (!bridgeUrl || !appKey) throw new Error("Hue Bridge URL en app key zijn verplicht.");
  await query(
    `insert into hue_config (household_id, bridge_url, app_key, updated_at)
     values ($1, $2, $3, now())
     on conflict (household_id) do update set bridge_url = excluded.bridge_url, app_key = excluded.app_key, updated_at = now()`,
    [localIds.householdId, bridgeUrl.replace(/\/$/, ""), appKey],
  );
  revalidatePath("/home");
  revalidatePath("/instellingen");
}

async function saveLocalGoogleHomeIntegration(formData: FormData) {
  await ensureLocalActionUser();
  const mode = value(formData, "mode") === "nest_sdm" ? "nest_sdm" : "home_apis";
  const projectId = value(formData, "project_id") || process.env.GOOGLE_HOME_PROJECT_ID || "";
  const clientId = value(formData, "client_id") || process.env.GOOGLE_HOME_CLIENT_ID || "";
  const clientSecret = value(formData, "client_secret") || process.env.GOOGLE_HOME_CLIENT_SECRET || "";
  if (mode === "nest_sdm" && (!projectId || !clientId || !clientSecret)) {
    throw new Error("Nest SDM vereist een Device Access project ID, OAuth client ID en client secret.");
  }
  await query(
    `insert into smart_home_integrations (household_id, provider, mode, status, display_name, project_id, client_id, client_secret)
     values ($1, 'google_home', $2, 'needs_auth', $3, $4, $5, $6)
     on conflict (household_id, provider, mode) do update set
       status = 'needs_auth',
       display_name = excluded.display_name,
       project_id = excluded.project_id,
       client_id = excluded.client_id,
       client_secret = excluded.client_secret`,
    [localIds.householdId, mode, mode === "nest_sdm" ? "Google Nest SDM" : "Google Home", projectId, clientId, clientSecret],
  );
  revalidatePath("/home");
  revalidatePath("/instellingen");
}

async function saveLocalOutlookOAuthConfig(formData: FormData) {
  const user = await ensureLocalActionUser();
  const clientId = value(formData, "client_id")?.trim();
  const clientSecret = value(formData, "client_secret")?.trim();
  const tenantId = value(formData, "tenant_id")?.trim() || "consumers";
  if (!clientId || !clientSecret) throw new Error("Vul de Application (client) ID en de client secret value in.");

  const membership = await query<{ role: string }>(
    "select role from household_members where household_id = $1 and user_id = $2",
    [localIds.householdId, user.id],
  );
  if (membership.rows[0]?.role !== "owner" && membership.rows[0]?.role !== "admin") {
    throw new Error("Alleen een beheerder kan de Outlook app-configuratie wijzigen.");
  }

  await query(
    `insert into outlook_oauth_config (household_id, client_id, client_secret, tenant_id, updated_at)
     values ($1, $2, $3, $4, now())
     on conflict (household_id) do update set
       client_id = excluded.client_id,
       client_secret = excluded.client_secret,
       tenant_id = excluded.tenant_id,
       updated_at = now()`,
    [localIds.householdId, clientId, clientSecret, tenantId],
  );
  revalidatePath("/agenda");
  revalidatePath("/instellingen");
}

async function saveLocalBunqConnection(formData: FormData) {
  await ensureLocalActionUser();
  const apiKey = value(formData, "api_key");
  const environment = value(formData, "environment") === "production" ? "production" : "sandbox";
  const oauthClientId = value(formData, "oauth_client_id") || process.env.BUNQ_OAUTH_CLIENT_ID || null;
  const oauthClientSecret = value(formData, "oauth_client_secret") || process.env.BUNQ_OAUTH_CLIENT_SECRET || null;
  if (!apiKey && (!oauthClientId || !oauthClientSecret)) throw new Error("Vul een bunq API key of OAuth clientgegevens in.");
  await query(
    `insert into bank_connections (household_id, provider, environment, secret_api_key, oauth_client_id, oauth_client_secret, status)
     values ($1, 'bunq', $2, $3, $4, $5, 'needs_session')
     on conflict (household_id, provider) do update set
       environment = excluded.environment,
       secret_api_key = excluded.secret_api_key,
       oauth_client_id = excluded.oauth_client_id,
       oauth_client_secret = excluded.oauth_client_secret,
       status = 'needs_session'`,
    [localIds.householdId, environment, apiKey || null, oauthClientId, oauthClientSecret],
  );
  revalidatePath("/geld");
  revalidatePath("/instellingen");
}

async function saveLocalTaskIntegration(formData: FormData) {
  await ensureLocalActionUser();
  const provider = value(formData, "provider");
  if (provider !== "microsoft_todo" && provider !== "apple_reminders") return;
  const syncDirection = value(formData, "sync_direction") ?? (provider === "apple_reminders" ? "import_only" : "two_way");
  await query(
    `insert into task_integrations (household_id, provider, display_name, status, sync_direction, client_id, tenant_id)
     values ($1, $2, $3, $4, $5, $6, $7)
     on conflict (household_id, provider) do update set
       display_name = excluded.display_name,
       status = excluded.status,
       sync_direction = excluded.sync_direction,
       client_id = excluded.client_id,
       tenant_id = excluded.tenant_id`,
    [
      localIds.householdId,
      provider,
      provider === "microsoft_todo" ? "Microsoft To Do" : "Apple Herinneringen",
      provider === "microsoft_todo" ? "needs_auth" : "planned",
      syncDirection,
      value(formData, "client_id"),
      value(formData, "tenant_id"),
    ],
  );
  revalidatePath("/taken");
  revalidatePath("/instellingen");
}

async function toggleLocalTask(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  const status = value(formData, "status") === "done" ? "open" : "done";
  if (!id) return;
  const taskResult = await query<{
    title: string;
    description: string | null;
    assignee_id: string | null;
    priority: string;
    due_date: string | null;
    recurrence: string | null;
    parent_task_id: string | null;
  }>("select title, description, assignee_id, priority, due_date, recurrence, parent_task_id from tasks where id = $1 and household_id = $2", [
    id,
    localIds.householdId,
  ]);
  const task = taskResult.rows[0];
  if (!task) return;
  await query("update tasks set status = $1, completed_at = case when $1 = 'done' then now() else null end where id = $2 and household_id = $3", [
    status,
    id,
    localIds.householdId,
  ]);
  if (status === "done" && !task.parent_task_id && task.due_date) {
    const nextDueDate = nextRecurringDate(task.due_date, normalizeTaskRecurrence(task.recurrence));
    if (nextDueDate) {
      await query(
        `insert into tasks (household_id, title, description, assignee_id, priority, due_date, recurrence)
         select $1, $2, $3, $4, $5, $6::date, $7
         where not exists (
           select 1 from tasks
           where household_id = $1 and title = $2 and coalesce(assignee_id::text, '') = coalesce($4::uuid::text, '')
             and due_date = $6::date and status = 'open' and parent_task_id is null
         )`,
        [localIds.householdId, task.title, task.description, task.assignee_id, task.priority, nextDueDate, task.recurrence],
      );
    }
  }
  revalidateCorePaths();
}

async function deleteLocalTask(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from tasks where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

async function addLocalShoppingItem(formData: FormData) {
  await ensureLocalActionUser();
  const name = value(formData, "name");
  if (!name) return;
  const category = value(formData, "category");
  const quantity = value(formData, "quantity");
  const recurrence = value(formData, "recurrence") ?? "none";
  const totalPriceCents = centsFromEuros(value(formData, "price"));
  const store = value(formData, "store");

  const product = await query<{ id: string }>(
    `insert into shopping_products (household_id, name, category, default_quantity, recurrence)
     values ($1, $2, $3, $4, $5)
     on conflict (household_id, name) do update set
       category = excluded.category,
       default_quantity = excluded.default_quantity,
       recurrence = excluded.recurrence
     returning id`,
    [localIds.householdId, name, category, quantity, recurrence],
  );

  await query(
    "insert into shopping_items (household_id, list_id, product_id, name, quantity, category) values ($1, $2, $3, $4, $5, $6)",
    [localIds.householdId, localIds.listId, product.rows[0]?.id, name, quantity, category],
  );

  if (totalPriceCents !== null) {
    await query(
      "insert into price_observations (household_id, product_id, product_name, store, total_price_cents, quantity, source) values ($1, $2, $3, $4, $5, $6, 'manual')",
      [localIds.householdId, product.rows[0]?.id, name, store, totalPriceCents, quantity],
    );
  }
  await insertLocalFreeShoppingPrices([{
    id: "new-item",
    household_id: localIds.householdId,
    list_id: localIds.listId,
    product_id: product.rows[0]?.id,
    name,
    category,
    quantity,
    checked: false,
  }]);
  revalidateCorePaths();
}

async function toggleLocalShoppingItem(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  const checked = value(formData, "checked") !== "true";
  if (!id) return;
  await query("update shopping_items set checked = $1 where id = $2 and household_id = $3", [checked, id, localIds.householdId]);
  if (checked) {
    await query(
      `update shopping_products
       set purchase_count = purchase_count + 1, last_purchased_at = now()
       where id = (select product_id from shopping_items where id = $1 and household_id = $2)`,
      [id, localIds.householdId],
    );
  }
  revalidateCorePaths();
}

async function deleteLocalShoppingItem(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from shopping_items where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

async function clearLocalCheckedShoppingItems() {
  await ensureLocalActionUser();
  await query("delete from shopping_items where household_id = $1 and checked = true", [localIds.householdId]);
  revalidateCorePaths();
}

async function addLocalRecurringProductToShopping(formData: FormData) {
  await ensureLocalActionUser();
  const productId = value(formData, "product_id");
  if (!productId) return;
  const product = await query<{ id: string; name: string; category: string | null; default_quantity: string | null }>(
    "select id, name, category, default_quantity from shopping_products where id = $1 and household_id = $2",
    [productId, localIds.householdId],
  );
  const item = product.rows[0];
  if (!item) return;
  await query(
    `insert into shopping_items (household_id, list_id, product_id, name, quantity, category)
     select $1, $2, $3, $4, $5, $6
     where not exists (
       select 1 from shopping_items
       where household_id = $1 and product_id = $3 and checked = false
     )`,
    [localIds.householdId, localIds.listId, item.id, item.name, item.default_quantity, item.category],
  );
  revalidateCorePaths();
}

async function addLocalFinanceItem(formData: FormData) {
  await ensureLocalActionUser();
  const title = value(formData, "title");
  const amountCents = centsFromEuros(value(formData, "amount"));
  if (!title || amountCents === null) return;
  await query(
    `insert into finance_items (household_id, title, category, amount_cents, frequency, due_date, status)
     values ($1, $2, $3, $4, $5, nullif($6, '')::date, $7)`,
    [
      localIds.householdId,
      title,
      value(formData, "category") ?? "Algemeen",
      amountCents,
      value(formData, "frequency") ?? "maandelijks",
      value(formData, "due_date"),
      value(formData, "status") ?? "actief",
    ],
  );
  revalidateCorePaths();
}

async function deleteLocalFinanceItem(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from finance_items where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

async function markLocalFinanceItemPaid(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  const result = await query<{
    title: string;
    category: string;
    amount_cents: number;
    frequency: string;
    due_date: string | null;
  }>("select title, category, amount_cents, frequency, due_date from finance_items where id = $1 and household_id = $2", [
    id,
    localIds.householdId,
  ]);
  const item = result.rows[0];
  if (!item) return;
  await query("update finance_items set status = 'betaald' where id = $1 and household_id = $2", [id, localIds.householdId]);
  const nextDueDate = nextFinanceDate(item.due_date, item.frequency);
  if (nextDueDate) {
    await query(
      `insert into finance_items (household_id, title, category, amount_cents, frequency, due_date, status)
       select $1, $2, $3, $4, $5, $6::date, 'actief'
       where not exists (
         select 1 from finance_items
         where household_id = $1 and title = $2 and due_date = $6::date and status <> 'betaald'
       )`,
      [localIds.householdId, item.title, item.category, item.amount_cents, item.frequency, nextDueDate],
    );
  }
  revalidateCorePaths();
}

async function addLocalCalendarEvent(formData: FormData) {
  await ensureLocalActionUser();
  const title = value(formData, "title");
  const startsAt = value(formData, "starts_at");
  if (!title || !startsAt) return;
  await query(
    `insert into calendar_events (household_id, title, starts_at, ends_at, location, participant_ids)
     values ($1, $2, $3::timestamptz, nullif($4, '')::timestamptz, $5, $6::uuid[])`,
    [
      localIds.householdId,
      title,
      startsAt,
      value(formData, "ends_at"),
      value(formData, "location"),
      formData.getAll("participant_ids").filter((item): item is string => typeof item === "string" && Boolean(item)),
    ],
  );
  revalidateCorePaths();
}

async function deleteLocalCalendarEvent(formData: FormData) {
  await ensureLocalActionUser();
  const id = value(formData, "id");
  if (!id) return;
  await query("delete from calendar_events where id = $1 and household_id = $2", [id, localIds.householdId]);
  revalidateCorePaths();
}

function revalidateCorePaths() {
  revalidatePath("/");
  revalidatePath("/vandaag");
  revalidatePath("/week");
  revalidatePath("/activiteit");
  revalidatePath("/meldingen");
  revalidatePath("/snel");
  revalidatePath("/routines");
  revalidatePath("/wie-doet-wat");
  revalidatePath("/koppelingen");
  revalidatePath("/noodkaart");
  revalidatePath("/inrichting");
  revalidatePath("/data");
  revalidatePath("/wishlist");
  revalidatePath("/gezin");
  revalidatePath("/adresboek");
  revalidatePath("/onderhoud");
  revalidatePath("/prikbord");
  revalidatePath("/documenten");
  revalidatePath("/boodschappen");
  revalidatePath("/taken");
  revalidatePath("/boodschappen");
  revalidatePath("/geld");
  revalidatePath("/agenda");
}

async function ensureLocalActionUser() {
  const user = await getLocalUser();
  if (!user) redirect("/login");
  return user;
}

function normalizeTaskRecurrence(recurrence: string | null) {
  if (recurrence === "daily" || recurrence === "weekly" || recurrence === "monthly") return recurrence;
  return "none";
}

function normalizeWishlistPriority(priority: string | null) {
  if (priority === "laag" || priority === "hoog") return priority;
  return "normaal";
}

function normalizeWishlistStatus(status: string | null) {
  if (status === "reserved" || status === "purchased") return status;
  return "open";
}

function normalizeWishlistPurchaseMode(mode: string | null) {
  if (mode === "repeatable") return "repeatable";
  return "single";
}

function normalizeOptionalUrl(url: string | null) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    return parsed.toString();
  } catch {
    return null;
  }
}

function nextRecurringDate(dateValue: string, recurrence: string) {
  if (recurrence === "none") return null;
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  if (Number.isNaN(date.getTime())) return null;
  if (recurrence === "daily") date.setUTCDate(date.getUTCDate() + 1);
  if (recurrence === "weekly") date.setUTCDate(date.getUTCDate() + 7);
  if (recurrence === "monthly") date.setUTCMonth(date.getUTCMonth() + 1);
  return date.toISOString().slice(0, 10);
}

function normalizeContactPriority(priority: string | null) {
  if (priority === "nood" || priority === "belangrijk") return priority;
  return "normaal";
}

function normalizeContactType(type: string | null) {
  if (type === "gezin" || type === "organisatie") return type;
  return "persoon";
}

function validBirthDate(value: string | null) {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

function normalizeMealType(mealType: string | null) {
  if (mealType === "ontbijt" || mealType === "lunch" || mealType === "snack") return mealType;
  return "avondeten";
}

function parseIngredients(ingredients: string) {
  return ingredients
    .split(/\r?\n|,/)
    .map((ingredient) => ingredient.trim())
    .filter(Boolean)
    .slice(0, 40);
}

function uniqueParsedIngredients(ingredients: string[]) {
  const seen = new Set<string>();
  return ingredients.filter((ingredient) => {
    const key = ingredient.trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 80);
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function quickDateTime(dateValue: string | null) {
  if (!dateValue) return new Date().toISOString();
  return `${dateValue}T09:00:00.000+01:00`;
}

function normalizeMaintenanceFrequency(frequency: string | null) {
  if (frequency === "monthly" || frequency === "quarterly" || frequency === "yearly") return frequency;
  return "none";
}

function nextMaintenanceDate(dateValue: string | null, frequency: string) {
  if (!dateValue || frequency === "none") return null;
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  if (Number.isNaN(date.getTime())) return null;
  if (frequency === "monthly") date.setUTCMonth(date.getUTCMonth() + 1);
  if (frequency === "quarterly") date.setUTCMonth(date.getUTCMonth() + 3);
  if (frequency === "yearly") date.setUTCFullYear(date.getUTCFullYear() + 1);
  return date.toISOString().slice(0, 10);
}

function nextFinanceDate(dateValue: string | null, frequency: string) {
  if (!dateValue || frequency === "eenmalig") return null;
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  if (Number.isNaN(date.getTime())) return null;
  if (frequency === "maandelijks") date.setUTCMonth(date.getUTCMonth() + 1);
  if (frequency === "jaarlijks") date.setUTCFullYear(date.getUTCFullYear() + 1);
  return date.toISOString().slice(0, 10);
}

function inferManualTransactionCategory(input: string) {
  const value = input.toLowerCase();
  if (/(ah|albert heijn|jumbo|lidl|kaufland|aldi|plus|supermarkt|picnic)/.test(value)) return "Boodschappen";
  if (/(huur|hypotheek|energie|eneco|vattenfall|essent|waternet|ziggo|kpn|odido|vodafone)/.test(value)) return "Wonen";
  if (/(salaris|loon|uitkering|belastingdienst)/.test(value)) return "Inkomen";
  if (/(ns |ov-chip|shell|esso|bp |total|parkeren|q-park)/.test(value)) return "Vervoer";
  if (/(zorg|verzekering|cz |zilveren kruis|vgz|aevitae)/.test(value)) return "Zorg";
  if (/(spotify|netflix|disney|apple|google|microsoft|adobe)/.test(value)) return "Abonnementen";
  return "Ongecategoriseerd";
}

async function insertLocalFreeShoppingPrices(items: ShoppingItem[]) {
  if (getShoppingPriceProviderStatus().id !== "checkjebon") return;
  try {
    const [prices, offers, kauflandPrices] = await Promise.all([fetchFreeShoppingPrices(items), fetchPrijsProfeetOffers(items), fetchKauflandPrices(items)]);
    for (const price of prices) {
      await query(
        `insert into price_observations
          (household_id, product_id, product_name, store, unit_price_cents, total_price_cents, quantity, source, external_url, price_provider, reliability, matched_product_name)
         values ($1, $2, $3, $4, $5, $5, $6, 'price_check', $7, 'checkjebon', 'indicatief', $8)`,
        [localIds.householdId, price.productId, price.queryName, price.store, price.totalPriceCents, price.quantity, price.externalUrl, price.productName],
      );
    }
    for (const offer of offers) {
      await query(
        `insert into price_observations
          (household_id, product_id, product_name, store, unit_price_cents, total_price_cents, quantity, source, regular_price_cents, offer_label, offer_valid_until, external_url, price_provider, reliability, matched_product_name)
         values ($1, $2, $3, $4, $5, $5, null, 'price_check', $6, $7, $8, $9, 'prijsprofeet', 'aanbieding', $10)`,
        [localIds.householdId, offer.productId, offer.queryName, offer.store, offer.totalPriceCents, offer.regularPriceCents, offer.offerLabel, offer.offerValidUntil, offer.externalUrl, offer.matchedProductName],
      );
    }
    for (const price of kauflandPrices) {
      await query(
        `insert into price_observations
          (household_id, product_id, product_name, store, unit_price_cents, total_price_cents, quantity, source, external_url, price_provider, reliability, matched_product_name)
         values ($1, $2, $3, 'Kaufland DE', $4, $4, $5, 'price_check', $6, 'apify', 'live_gecontroleerd', $7)`,
        [localIds.householdId, price.productId, price.queryName, price.totalPriceCents, price.quantity, price.externalUrl, price.matchedProductName],
      );
    }
  } catch (error) {
    console.error("Boodschappen prijscheck mislukt", error);
  }
}
