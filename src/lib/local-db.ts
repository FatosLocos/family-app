import { Pool, type QueryResultRow } from "pg";
import type {
  AppData,
  BankAccount,
  CalendarEvent,
  CalendarIntegration,
  IcsCalendarFileImport,
  IcsCalendarSubscription,
  FinanceBudget,
  FinanceItem,
  Household,
  HouseholdBirthday,
  HouseholdContact,
  HouseholdContactMember,
  HouseholdDocument,
  HouseholdInfoItem,
  HouseholdMember,
  HouseholdNote,
  HouseholdPreferences,
  MaintenanceItem,
  MealPlan,
  PriceObservation,
  RecurringTransactionRule,
  SmartHomeDevice,
  SmartHomeIntegration,
  ShoppingItem,
  ShoppingList,
  ShoppingProduct,
  ShoppingScan,
  Task,
  TaskIntegration,
  BankConnection,
  BankTransaction,
  WishlistItem,
  WishlistShare,
} from "@/lib/types";

const householdId = "00000000-0000-4000-8000-000000000001";
const userId = "00000000-0000-4000-8000-000000000001";
const listId = "00000000-0000-4000-8000-000000000001";

let pool: Pool | null = null;
let initialized = false;
let initializePromise: Promise<void> | null = null;

function getPool() {
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL ontbreekt.");
  pool ??= new Pool({ connectionString: process.env.DATABASE_URL });
  return pool;
}

export async function query<T extends QueryResultRow = QueryResultRow>(text: string, params: unknown[] = []) {
  await ensureLocalSchema();
  return getPool().query<T>(text, params);
}

export async function ensureLocalSchema() {
  if (initialized) return;
  if (initializePromise) return initializePromise;
  initializePromise = initializeLocalSchema();
  await initializePromise;
}

async function initializeLocalSchema() {
  const db = getPool();
  await db.query(`
    create extension if not exists pgcrypto;

    create table if not exists households (
      id uuid primary key,
      name text not null,
      owner_id uuid not null
    );

    create table if not exists household_preferences (
      household_id uuid primary key references households(id) on delete cascade,
      week_starts_on text not null default 'monday',
      default_dashboard text not null default 'vandaag',
      default_shopping_store text,
      quiet_hours_start text,
      quiet_hours_end text,
      updated_at timestamptz not null default now()
    );

    alter table household_preferences add column if not exists week_starts_on text not null default 'monday';
    alter table household_preferences add column if not exists default_dashboard text not null default 'vandaag';
    alter table household_preferences add column if not exists default_shopping_store text;
    alter table household_preferences add column if not exists quiet_hours_start text;
    alter table household_preferences add column if not exists quiet_hours_end text;
    alter table household_preferences add column if not exists updated_at timestamptz not null default now();

    create table if not exists profiles (
      id uuid primary key,
      full_name text,
      email text,
      password_hash text,
      phone text,
      avatar_color text,
      notification_email boolean not null default true,
      digest_time text,
      created_at timestamptz not null default now()
    );

    alter table profiles add column if not exists password_hash text;
    alter table profiles add column if not exists phone text;
    alter table profiles add column if not exists avatar_color text;
    alter table profiles add column if not exists notification_email boolean not null default true;
    alter table profiles add column if not exists digest_time text;
    alter table profiles add column if not exists created_at timestamptz not null default now();
    create unique index if not exists profiles_email_unique on profiles (lower(email)) where email is not null;

    create table if not exists household_members (
      household_id uuid not null references households(id) on delete cascade,
      user_id uuid not null references profiles(id) on delete cascade,
      role text not null default 'member',
      created_at timestamptz not null default now(),
      primary key (household_id, user_id)
    );

    create table if not exists local_sessions (
      id uuid primary key default gen_random_uuid(),
      user_id uuid not null references profiles(id) on delete cascade,
      token_hash text not null unique,
      expires_at timestamptz not null,
      last_seen_at timestamptz not null default now(),
      created_at timestamptz not null default now()
    );

    alter table local_sessions add column if not exists last_seen_at timestamptz not null default now();
    create index if not exists local_sessions_user_id_idx on local_sessions(user_id);
    create index if not exists local_sessions_expires_at_idx on local_sessions(expires_at);

    create table if not exists household_contacts (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      name text not null,
      relationship text,
      phone text,
      email text,
      address text,
      notes text,
      priority text not null default 'normaal',
      created_at timestamptz not null default now()
    );

    alter table household_contacts add column if not exists contact_type text not null default 'persoon';
    alter table household_contacts add column if not exists postal_code text;
    alter table household_contacts add column if not exists city text;
    alter table household_contacts add column if not exists country text;

    create table if not exists household_birthdays (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      name text not null,
      birth_date date not null,
      relation text,
      member_id uuid references profiles(id) on delete set null,
      notes text,
      created_at timestamptz not null default now(),
      unique (household_id, name, birth_date)
    );

    create table if not exists household_contact_members (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      contact_id uuid not null references household_contacts(id) on delete cascade,
      name text not null,
      relationship text,
      birth_date date,
      phone text,
      email text,
      notes text,
      created_at timestamptz not null default now(),
      unique (contact_id, name, birth_date)
    );

    alter table household_birthdays add column if not exists contact_member_id uuid references household_contact_members(id) on delete set null;
    create index if not exists household_contact_members_household_idx on household_contact_members (household_id, contact_id, name);

    create table if not exists household_info_items (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      category text not null default 'Algemeen',
      value text,
      notes text,
      is_sensitive boolean not null default false,
      created_at timestamptz not null default now()
    );

    create table if not exists maintenance_items (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      area text,
      provider text,
      due_date date,
      frequency text not null default 'none',
      status text not null default 'open',
      notes text,
      completed_at timestamptz,
      created_at timestamptz not null default now()
    );

    create table if not exists household_notes (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      body text not null,
      category text not null default 'Algemeen',
      pinned boolean not null default false,
      expires_at date,
      created_by uuid references profiles(id) on delete set null,
      created_at timestamptz not null default now()
    );

    create table if not exists household_documents (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      category text not null default 'Algemeen',
      owner_name text,
      location text,
      reference text,
      expires_at date,
      notes text,
      is_sensitive boolean not null default false,
      created_at timestamptz not null default now()
    );

    create table if not exists tasks (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      description text,
      assignee_id uuid,
      status text not null default 'open',
      priority text not null default 'normaal',
      due_date date,
      recurrence text not null default 'none',
      parent_task_id uuid references tasks(id) on delete cascade,
      completed_at timestamptz,
      created_at timestamptz not null default now()
    );

    alter table tasks add column if not exists recurrence text not null default 'none';
    alter table tasks add column if not exists parent_task_id uuid references tasks(id) on delete cascade;
    alter table tasks add column if not exists completed_at timestamptz;
    create index if not exists tasks_parent_task_id_idx on tasks(parent_task_id);

    create table if not exists shopping_lists (
      id uuid primary key,
      household_id uuid not null references households(id) on delete cascade,
      name text not null,
      created_at timestamptz not null default now()
    );

    create table if not exists shopping_products (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      name text not null,
      category text,
      default_quantity text,
      recurrence text not null default 'none',
      purchase_count integer not null default 0,
      last_purchased_at timestamptz,
      created_at timestamptz not null default now(),
      unique (household_id, name)
    );

    create table if not exists shopping_items (
      id uuid primary key default gen_random_uuid(),
      list_id uuid not null references shopping_lists(id) on delete cascade,
      household_id uuid not null references households(id) on delete cascade,
      product_id uuid references shopping_products(id) on delete set null,
      name text not null,
      category text,
      quantity text,
      checked boolean not null default false,
      created_at timestamptz not null default now()
    );

    create table if not exists meal_plans (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      planned_date date not null,
      meal_type text not null default 'avondeten',
      title text not null,
      notes text,
      ingredients text,
      created_at timestamptz not null default now()
    );

    create table if not exists price_observations (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      product_id uuid references shopping_products(id) on delete set null,
      product_name text not null,
      store text,
      observed_at timestamptz not null default now(),
      unit_price_cents integer,
      total_price_cents integer not null,
      quantity text,
      source text not null default 'manual',
      regular_price_cents integer,
      offer_label text,
      offer_valid_until date,
      external_url text,
      price_provider text,
      reliability text,
      matched_product_name text
    );

    alter table price_observations add column if not exists regular_price_cents integer;
    alter table price_observations add column if not exists offer_label text;
    alter table price_observations add column if not exists offer_valid_until date;
    alter table price_observations add column if not exists external_url text;
    alter table price_observations add column if not exists price_provider text;
    alter table price_observations add column if not exists reliability text;
    alter table price_observations add column if not exists matched_product_name text;

    create table if not exists shopping_scans (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      status text not null default 'queued',
      source_filename text,
      extracted_text text,
      created_at timestamptz not null default now()
    );

    create table if not exists finance_items (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      category text not null default 'Algemeen',
      amount_cents integer not null,
      frequency text not null default 'maandelijks',
      due_date date,
      status text not null default 'actief',
      created_at timestamptz not null default now()
    );

    create table if not exists finance_budgets (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      category text not null,
      monthly_limit_cents integer not null,
      alert_threshold numeric not null default 0.8,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (household_id, category)
    );

    create table if not exists calendar_events (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      integration_id uuid,
      external_event_id text,
      external_calendar_id text,
      external_calendar_name text,
      title text not null,
      starts_at timestamptz not null,
      ends_at timestamptz,
      location text,
      participant_ids uuid[] not null default '{}',
      is_all_day boolean not null default false,
      source_provider text,
      organizer_name text,
      web_link text,
      raw jsonb,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (integration_id, external_event_id)
    );

    create table if not exists home_assistant_config (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade unique,
      base_url text not null,
      token text not null,
      updated_at timestamptz not null default now()
    );

    create table if not exists hue_config (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade unique,
      bridge_url text not null,
      app_key text not null,
      updated_at timestamptz not null default now()
    );

    create table if not exists smart_home_integrations (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      provider text not null,
      mode text not null,
      status text not null default 'needs_auth',
      display_name text not null,
      project_id text,
      client_id text,
      client_secret text,
      secret_refresh_token text,
      access_token text,
      expires_at timestamptz,
      last_sync_at timestamptz,
      unique (household_id, provider, mode)
    );

    create table if not exists smart_home_devices (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      integration_id uuid not null references smart_home_integrations(id) on delete cascade,
      provider_device_id text not null,
      name text not null,
      type text,
      room text,
      traits jsonb not null default '{}',
      state jsonb not null default '{}',
      updated_at timestamptz not null default now(),
      unique (integration_id, provider_device_id)
    );

    create table if not exists calendar_integrations (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      user_id uuid not null references profiles(id) on delete cascade,
      provider text not null,
      status text not null default 'needs_auth',
      display_name text not null,
      account_email text,
      tenant_id text not null default 'consumers',
      client_id text not null,
      client_secret text not null,
      secret_refresh_token text,
      access_token text,
      expires_at timestamptz,
      last_sync_at timestamptz,
      unique (household_id, user_id, provider)
    );

    create table if not exists outlook_oauth_config (
      household_id uuid primary key references households(id) on delete cascade,
      client_id text not null,
      client_secret text not null,
      tenant_id text not null default 'consumers',
      updated_at timestamptz not null default now()
    );

    create table if not exists ics_calendar_subscriptions (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      user_id uuid not null references profiles(id) on delete cascade,
      display_name text not null,
      feed_url text not null,
      status text not null default 'configured',
      last_sync_at timestamptz,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (household_id, user_id, feed_url)
    );

    create table if not exists ics_calendar_file_imports (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      user_id uuid not null references profiles(id) on delete cascade,
      display_name text not null,
      file_name text not null,
      status text not null default 'configured' check (status in ('configured', 'sync_error')),
      last_imported_at timestamptz,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (household_id, user_id, display_name)
    );

    create table if not exists bank_connections (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      provider text not null,
      environment text not null default 'sandbox',
      secret_api_key text,
      oauth_client_id text,
      oauth_client_secret text,
      oauth_access_token text,
      oauth_token_type text,
      oauth_connected_at timestamptz,
      status text not null default 'needs_session',
      session_token text,
      last_sync_at timestamptz,
      created_at timestamptz not null default now(),
      unique (household_id, provider)
    );

    alter table bank_connections add column if not exists oauth_client_id text;
    alter table bank_connections add column if not exists oauth_client_secret text;
    alter table bank_connections add column if not exists oauth_access_token text;
    alter table bank_connections add column if not exists oauth_token_type text;
    alter table bank_connections add column if not exists oauth_connected_at timestamptz;

    create table if not exists bank_accounts (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      connection_id uuid not null references bank_connections(id) on delete cascade,
      provider_account_id text not null,
      name text not null,
      iban text,
      currency text not null default 'EUR',
      balance_cents integer,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (connection_id, provider_account_id)
    );

    create table if not exists bank_transactions (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      connection_id uuid not null references bank_connections(id) on delete cascade,
      account_id uuid references bank_accounts(id) on delete set null,
      provider_transaction_id text not null,
      booked_at timestamptz not null,
      description text not null,
      counterparty text,
      amount_cents integer not null,
      currency text not null default 'EUR',
      category text,
      raw jsonb not null default '{}',
      created_at timestamptz not null default now(),
      unique (connection_id, provider_transaction_id)
    );

    create table if not exists recurring_transaction_rules (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      rule_key text not null,
      label text not null,
      action text not null check (action in ('force_recurring', 'exclude_recurring', 'group_recurring')),
      group_id text,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (household_id, rule_key)
    );

    alter table recurring_transaction_rules add column if not exists group_id text;
    alter table recurring_transaction_rules drop constraint if exists recurring_transaction_rules_action_check;
    alter table recurring_transaction_rules add constraint recurring_transaction_rules_action_check
      check (action in ('force_recurring', 'exclude_recurring', 'group_recurring'));

    create table if not exists task_integrations (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      provider text not null,
      display_name text not null,
      status text not null default 'needs_auth',
      sync_direction text not null default 'two_way',
      client_id text,
      tenant_id text,
      last_sync_at timestamptz,
      unique (household_id, provider)
    );

    create table if not exists wishlist_shares (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null default 'Verlanglijst',
      public_token text not null unique,
      enabled boolean not null default true,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (household_id)
    );

    create table if not exists wishlist_items (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      title text not null,
      description text,
      url text,
      image_url text,
      desired_by text,
      category text,
      price_cents integer check (price_cents is null or price_cents >= 0),
      priority text not null default 'normaal',
      status text not null default 'open',
      purchase_mode text not null default 'single',
      purchase_count integer not null default 0,
      is_public boolean not null default false,
      reserved_by_name text,
      reserved_at timestamptz,
      purchased_at timestamptz,
      last_purchased_at timestamptz,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
    );

    alter table wishlist_items add column if not exists purchase_mode text not null default 'single';
    alter table wishlist_items add column if not exists purchase_count integer not null default 0;
    alter table wishlist_items add column if not exists last_purchased_at timestamptz;

    create index if not exists wishlist_items_household_id_idx on wishlist_items(household_id);
    create index if not exists wishlist_items_public_idx on wishlist_items(household_id, is_public, status);

    create table if not exists household_invites (
      id uuid primary key default gen_random_uuid(),
      household_id uuid not null references households(id) on delete cascade,
      code text not null unique,
      invited_by uuid not null references profiles(id) on delete cascade,
      accepted_by uuid references profiles(id) on delete set null,
      expires_at timestamptz not null,
      accepted_at timestamptz,
      created_at timestamptz not null default now()
    );

    create index if not exists household_invites_household_id_idx on household_invites(household_id);
    create index if not exists household_invites_code_idx on household_invites(code);
  `);

  await db.query(
    `
    insert into profiles (id, full_name, email)
    values ($1, 'Fatih', 'family@example.com')
    on conflict (id) do nothing;
  `,
    [userId],
  );

  await db.query(
    `
    insert into households (id, name, owner_id)
    values ($1, 'Ons gezin', $2)
    on conflict (id) do nothing;
  `,
    [householdId, userId],
  );

  await db.query(
    `
    insert into household_preferences (household_id)
    values ($1)
    on conflict (household_id) do nothing;
  `,
    [householdId],
  );

  await db.query(
    `
    insert into household_members (household_id, user_id, role)
    values ($1, $2, 'owner')
    on conflict (household_id, user_id) do nothing;
  `,
    [householdId, userId],
  );

  await db.query(
    `
    insert into shopping_lists (id, household_id, name)
    values ($1, $2, 'Boodschappen')
    on conflict (id) do nothing;
  `,
    [listId, householdId],
  );
  initialized = true;
}

export async function getLocalAppData(): Promise<AppData> {
  await ensureLocalSchema();
  const db = getPool();
  const [
    householdResult,
    preferencesResult,
    membersResult,
    contactsResult,
    contactMembersResult,
    birthdaysResult,
    infoResult,
    maintenanceResult,
    notesResult,
    documentsResult,
    tasksResult,
    listsResult,
    itemsResult,
    productsResult,
    mealsResult,
    pricesResult,
    scansResult,
    financeResult,
    budgetResult,
    bankConnectionsResult,
    bankAccountsResult,
    bankTransactionsResult,
    recurringTransactionRulesResult,
    taskIntegrationsResult,
    calendarIntegrationsResult,
    icsCalendarSubscriptionsResult,
    icsCalendarFileImportsResult,
    calendarResult,
    homeAssistantResult,
    hueResult,
    smartHomeIntegrationsResult,
    smartHomeDevicesResult,
    wishlistItemsResult,
    wishlistSharesResult,
  ] = await Promise.all([
    db.query<Household>("select id, name, owner_id from households where id = $1", [householdId]),
    db.query<HouseholdPreferences>("select * from household_preferences where household_id = $1", [householdId]),
    db.query(
      `select hm.household_id, hm.user_id, hm.role, p.id as profile_id, p.full_name, p.email, p.phone, p.avatar_color,
        p.notification_email, p.digest_time
       from household_members hm
       join profiles p on p.id = hm.user_id
       where hm.household_id = $1
       order by hm.created_at`,
      [householdId],
    ),
    db.query<HouseholdContact>(
      "select * from household_contacts where household_id = $1 order by case priority when 'nood' then 0 when 'belangrijk' then 1 else 2 end, name",
      [householdId],
    ),
    db.query<HouseholdContactMember>(
      "select id, household_id, contact_id, name, relationship, birth_date::text as birth_date, phone, email, notes, created_at from household_contact_members where household_id = $1 order by name",
      [householdId],
    ),
    db.query<HouseholdBirthday>("select id, household_id, name, birth_date::text as birth_date, relation, member_id, contact_member_id, notes, created_at from household_birthdays where household_id = $1 order by birth_date, name", [householdId]),
    db.query<HouseholdInfoItem>("select * from household_info_items where household_id = $1 order by category, title", [householdId]),
    db.query<MaintenanceItem>(
      "select * from maintenance_items where household_id = $1 order by status, due_date nulls last, title",
      [householdId],
    ),
    db.query<HouseholdNote>(
      "select * from household_notes where household_id = $1 and (expires_at is null or expires_at >= current_date) order by pinned desc, created_at desc",
      [householdId],
    ),
    db.query<HouseholdDocument>(
      "select * from household_documents where household_id = $1 order by expires_at nulls last, category, title",
      [householdId],
    ),
    db.query<Task>("select * from tasks where household_id = $1 order by created_at desc", [householdId]),
    db.query<ShoppingList>("select * from shopping_lists where household_id = $1 order by created_at limit 1", [householdId]),
    db.query<ShoppingItem>("select * from shopping_items where household_id = $1 order by checked, created_at desc", [householdId]),
    db.query<ShoppingProduct>("select * from shopping_products where household_id = $1 order by purchase_count desc, name", [householdId]),
    db.query<MealPlan>(
      "select * from meal_plans where household_id = $1 and planned_date >= current_date - interval '1 day' order by planned_date asc, meal_type",
      [householdId],
    ),
    db.query<PriceObservation>("select * from price_observations where household_id = $1 order by observed_at desc limit 250", [householdId]),
    db.query<ShoppingScan>("select * from shopping_scans where household_id = $1 order by created_at desc limit 25", [householdId]),
    db.query<FinanceItem>("select * from finance_items where household_id = $1 order by due_date nulls last, created_at desc", [householdId]),
    db.query<FinanceBudget>("select * from finance_budgets where household_id = $1 order by category", [householdId]),
    db.query<BankConnection>(
      "select id, household_id, provider, environment, status, last_sync_at, oauth_connected_at, oauth_client_id from bank_connections where household_id = $1 order by created_at desc",
      [householdId],
    ),
    db.query<BankAccount>("select * from bank_accounts where household_id = $1 order by name", [householdId]),
    db.query<BankTransaction>("select * from bank_transactions where household_id = $1 order by booked_at desc limit 2000", [householdId]),
    db.query<RecurringTransactionRule>("select * from recurring_transaction_rules where household_id = $1 order by updated_at desc", [householdId]),
    db.query<TaskIntegration>("select id, household_id, provider, status, sync_direction, display_name, last_sync_at from task_integrations where household_id = $1", [householdId]),
    db.query<CalendarIntegration>(
      "select id, household_id, user_id, provider, status, display_name, account_email, tenant_id, last_sync_at from calendar_integrations where household_id = $1",
      [householdId],
    ),
    db.query<IcsCalendarSubscription>(
      "select id, household_id, user_id, display_name, status, last_sync_at from ics_calendar_subscriptions where household_id = $1 order by display_name",
      [householdId],
    ),
    db.query<IcsCalendarFileImport>(
      "select id, household_id, user_id, display_name, file_name, status, last_imported_at from ics_calendar_file_imports where household_id = $1 order by display_name",
      [householdId],
    ),
    db.query<CalendarEvent>("select * from calendar_events where household_id = $1 order by starts_at asc", [householdId]),
    db.query("select id from home_assistant_config where household_id = $1", [householdId]),
    db.query("select id from hue_config where household_id = $1", [householdId]),
    db.query<SmartHomeIntegration>(
      "select id, household_id, provider, mode, status, display_name, project_id, last_sync_at from smart_home_integrations where household_id = $1",
      [householdId],
    ),
    db.query<SmartHomeDevice>("select * from smart_home_devices where household_id = $1 order by name", [householdId]),
    db.query<WishlistItem>("select * from wishlist_items where household_id = $1 order by case status when 'open' then 0 when 'reserved' then 1 else 2 end, priority desc, created_at desc", [
      householdId,
    ]),
    db.query<WishlistShare>("select * from wishlist_shares where household_id = $1 order by created_at desc", [householdId]),
  ]);

  const members = membersResult.rows.map((member) => ({
    household_id: member.household_id,
    user_id: member.user_id,
    role: member.role,
    profile: {
      id: member.profile_id,
      full_name: member.full_name,
      email: member.email,
      phone: member.phone,
      avatar_color: member.avatar_color,
      notification_email: member.notification_email,
      digest_time: member.digest_time,
    },
  })) as HouseholdMember[];

  return {
    household: householdResult.rows[0],
    householdPreferences: preferencesResult.rows[0] ?? defaultHouseholdPreferences(),
    members,
    householdContacts: contactsResult.rows,
    householdContactMembers: contactMembersResult.rows,
    householdBirthdays: birthdaysResult.rows,
    householdInfoItems: infoResult.rows,
    maintenanceItems: maintenanceResult.rows,
    householdNotes: notesResult.rows,
    householdDocuments: documentsResult.rows,
    taskIntegrations: taskIntegrationsResult.rows,
    tasks: tasksResult.rows,
    shoppingList: listsResult.rows[0] ?? null,
    shoppingItems: itemsResult.rows,
    shoppingProducts: productsResult.rows,
    mealPlans: mealsResult.rows,
    priceObservations: pricesResult.rows,
    shoppingScans: scansResult.rows,
    financeItems: financeResult.rows,
    financeBudgets: budgetResult.rows,
    bankConnections: bankConnectionsResult.rows,
    bankAccounts: bankAccountsResult.rows,
    bankTransactions: bankTransactionsResult.rows,
    recurringTransactionRules: recurringTransactionRulesResult.rows,
    calendarIntegrations: calendarIntegrationsResult.rows,
    icsCalendarSubscriptions: icsCalendarSubscriptionsResult.rows,
    icsCalendarFileImports: icsCalendarFileImportsResult.rows,
    calendarEvents: calendarResult.rows.map(normalizeCalendarEvent),
    hasHomeAssistantConfig: homeAssistantResult.rows.length > 0 || Boolean(process.env.HOME_ASSISTANT_URL && process.env.HOME_ASSISTANT_TOKEN),
    hasHueConfig: hueResult.rows.length > 0 || Boolean(process.env.HUE_BRIDGE_URL && process.env.HUE_APP_KEY),
    smartHomeIntegrations: smartHomeIntegrationsResult.rows,
    smartHomeDevices: smartHomeDevicesResult.rows,
    wishlistItems: wishlistItemsResult.rows,
    wishlistShares: wishlistSharesResult.rows,
  };
}

export async function getPublicWishlistByToken(token: string) {
  await ensureLocalSchema();
  const db = getPool();
  const share = await db.query<WishlistShare>(
    "select * from wishlist_shares where public_token = $1 and enabled = true limit 1",
    [token],
  );
  const currentShare = share.rows[0];
  if (!currentShare) return null;
  const household = await db.query<Household>("select id, name, owner_id from households where id = $1", [currentShare.household_id]);
  const items = await db.query<WishlistItem>(
    `select *
     from wishlist_items
     where household_id = $1 and is_public = true
     order by case status when 'open' then 0 when 'reserved' then 1 else 2 end, priority desc, created_at desc`,
    [currentShare.household_id],
  );
  return {
    share: currentShare,
    household: household.rows[0],
    items: items.rows,
  };
}

export const localIds = { householdId, userId, listId };

function normalizeCalendarEvent(event: CalendarEvent): CalendarEvent {
  return {
    ...event,
    starts_at: normalizeTimestamp(event.starts_at),
    ends_at: event.ends_at ? normalizeTimestamp(event.ends_at) : null,
  };
}

function normalizeTimestamp(value: unknown) {
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "string") return value;
  throw new Error("Ongeldige datumwaarde uit PostgreSQL.");
}

export function defaultHouseholdPreferences(): HouseholdPreferences {
  return {
    household_id: householdId,
    week_starts_on: "monday",
    default_dashboard: "vandaag",
    default_shopping_store: null,
    quiet_hours_start: "22:00",
    quiet_hours_end: "07:00",
  };
}

export async function getLocalInvites() {
  await ensureLocalSchema();
  const { rows } = await getPool().query<{ id: string; code: string; expires_at: string; created_at: string }>(
    `select id, code, expires_at, created_at
     from household_invites
     where household_id = $1 and accepted_at is null and expires_at > now()
     order by created_at desc`,
    [householdId],
  );
  return rows;
}
