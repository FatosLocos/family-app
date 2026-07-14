export type Profile = {
  id: string;
  full_name: string | null;
  email: string | null;
  phone?: string | null;
  avatar_color?: string | null;
  notification_email?: boolean | null;
  digest_time?: string | null;
};

export type Household = {
  id: string;
  name: string;
  owner_id: string;
};

export type HouseholdPreferences = {
  household_id: string;
  week_starts_on: "monday" | "sunday";
  default_dashboard: "compact" | "uitgebreid" | "vandaag";
  default_shopping_store: string | null;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  updated_at?: string;
};

export type HouseholdMember = {
  household_id: string;
  user_id: string;
  role: "owner" | "admin" | "member";
  profile?: Profile | null;
};

export type HouseholdContact = {
  id: string;
  household_id: string;
  name: string;
  contact_type?: "persoon" | "gezin" | "organisatie";
  relationship: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  postal_code?: string | null;
  city?: string | null;
  country?: string | null;
  notes: string | null;
  priority: "normaal" | "belangrijk" | "nood";
  created_at?: string;
};

export type HouseholdContactMember = {
  id: string;
  household_id: string;
  contact_id: string;
  name: string;
  relationship: string | null;
  birth_date: string | null;
  phone: string | null;
  email: string | null;
  notes: string | null;
  created_at?: string;
};

export type HouseholdBirthday = {
  id: string;
  household_id: string;
  name: string;
  birth_date: string;
  relation: string | null;
  member_id: string | null;
  contact_member_id?: string | null;
  notes: string | null;
  created_at?: string;
};

export type HouseholdInfoItem = {
  id: string;
  household_id: string;
  title: string;
  category: string;
  value: string | null;
  notes: string | null;
  is_sensitive: boolean;
};

export type MaintenanceItem = {
  id: string;
  household_id: string;
  title: string;
  area: string | null;
  provider: string | null;
  due_date: string | null;
  frequency: "none" | "monthly" | "quarterly" | "yearly";
  status: "open" | "done";
  notes: string | null;
  completed_at: string | null;
  created_at?: string;
};

export type HouseholdNote = {
  id: string;
  household_id: string;
  title: string;
  body: string;
  category: string;
  pinned: boolean;
  expires_at: string | null;
  created_by: string | null;
  created_at: string;
};

export type HouseholdDocument = {
  id: string;
  household_id: string;
  title: string;
  category: string;
  owner_name: string | null;
  location: string | null;
  reference: string | null;
  expires_at: string | null;
  notes: string | null;
  is_sensitive: boolean;
  created_at: string;
};

export type Task = {
  id: string;
  household_id: string;
  title: string;
  description: string | null;
  assignee_id: string | null;
  status: "open" | "done";
  priority: "laag" | "normaal" | "hoog";
  due_date: string | null;
  recurrence?: "none" | "daily" | "weekly" | "monthly" | null;
  parent_task_id?: string | null;
  completed_at?: string | null;
  created_at?: string;
};

export type TaskIntegration = {
  id: string;
  household_id: string;
  provider: "microsoft_todo" | "apple_reminders";
  status: "planned" | "configured" | "needs_auth" | "sync_error";
  sync_direction: "import_only" | "export_only" | "two_way";
  display_name: string;
  last_sync_at: string | null;
};

export type ShoppingList = {
  id: string;
  household_id: string;
  name: string;
};

export type ShoppingItem = {
  id: string;
  list_id: string;
  household_id: string;
  product_id?: string | null;
  name: string;
  category: string | null;
  quantity: string | null;
  checked: boolean;
  created_at?: string;
};

export type ShoppingProduct = {
  id: string;
  household_id: string;
  name: string;
  category: string | null;
  default_quantity: string | null;
  recurrence: "none" | "weekly" | "biweekly" | "monthly";
  purchase_count: number;
  last_purchased_at: string | null;
};

export type MealPlan = {
  id: string;
  household_id: string;
  planned_date: string;
  meal_type: "ontbijt" | "lunch" | "avondeten" | "snack";
  title: string;
  notes: string | null;
  ingredients: string | null;
  created_at?: string;
};

export type PriceObservation = {
  id: string;
  household_id: string;
  product_id: string | null;
  product_name: string;
  store: string | null;
  observed_at: string;
  unit_price_cents: number | null;
  total_price_cents: number;
  quantity: string | null;
  source: "manual" | "ocr" | "bank" | "price_check";
  regular_price_cents?: number | null;
  offer_label?: string | null;
  offer_valid_until?: string | null;
  external_url?: string | null;
  price_provider?: "manual" | "checkjebon" | "prijsprofeet" | "apify" | "webscraping_amsterdam" | null;
  reliability?: "handmatig" | "indicatief" | "aanbieding" | "live_gecontroleerd" | "managed_feed" | null;
  matched_product_name?: string | null;
};

export type ShoppingScan = {
  id: string;
  household_id: string;
  status: "queued" | "processed" | "needs_review" | "failed";
  source_filename: string | null;
  extracted_text: string | null;
  created_at: string;
};

export type FinanceItem = {
  id: string;
  household_id: string;
  title: string;
  category: string;
  amount_cents: number;
  frequency: "eenmalig" | "maandelijks" | "jaarlijks";
  due_date: string | null;
  status: "actief" | "gepland" | "betaald";
  created_at?: string;
};

export type FinanceBudget = {
  id: string;
  household_id: string;
  category: string;
  monthly_limit_cents: number;
  alert_threshold: number;
};

export type BankConnection = {
  id: string;
  household_id: string;
  provider: "bunq" | "abn_amro_manual";
  environment: "sandbox" | "production";
  status: "configured" | "needs_session" | "sync_error";
  last_sync_at: string | null;
  oauth_connected_at?: string | null;
  oauth_client_id?: string | null;
};

export type BankAccount = {
  id: string;
  household_id: string;
  connection_id: string;
  provider_account_id: string;
  name: string;
  iban: string | null;
  currency: string;
  balance_cents: number | null;
};

export type BankTransaction = {
  id: string;
  household_id: string;
  connection_id: string;
  account_id: string | null;
  provider_transaction_id: string;
  booked_at: string;
  description: string;
  counterparty: string | null;
  amount_cents: number;
  currency: string;
  category: string | null;
  raw?: Record<string, unknown> | null;
};

export type RecurringTransactionRule = {
  id: string;
  household_id: string;
  rule_key: string;
  label: string;
  action: "force_recurring" | "exclude_recurring" | "group_recurring";
  group_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CalendarEvent = {
  id: string;
  household_id: string;
  integration_id?: string | null;
  external_event_id?: string | null;
  external_calendar_id?: string | null;
  external_calendar_name?: string | null;
  source_provider?: "outlook" | "ics" | null;
  title: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  participant_ids: string[];
  is_all_day?: boolean;
  organizer_name?: string | null;
  web_link?: string | null;
};

export type CalendarIntegration = {
  id: string;
  household_id: string;
  user_id: string;
  provider: "outlook";
  status: "needs_auth" | "configured" | "sync_error";
  display_name: string;
  account_email: string | null;
  tenant_id: string;
  last_sync_at: string | null;
};

export type IcsCalendarSubscription = {
  id: string;
  household_id: string;
  user_id: string;
  display_name: string;
  feed_url?: string;
  status: "configured" | "sync_error";
  last_sync_at: string | null;
};

export type IcsCalendarFileImport = {
  id: string;
  household_id: string;
  user_id: string;
  display_name: string;
  file_name: string;
  status: "configured" | "sync_error";
  last_imported_at: string | null;
};

export type HomeAssistantConfig = {
  id: string;
  household_id: string;
  base_url: string;
  token: string;
};

export type HomeAssistantState = {
  entity_id: string;
  state: string;
  attributes?: {
    friendly_name?: string;
    [key: string]: unknown;
  };
};

export type HueConfig = {
  id: string;
  household_id: string;
  bridge_url: string;
  app_key: string;
};

export type HueLight = {
  id: string;
  household_id?: string;
  rid: string;
  name: string;
  on: boolean;
  brightness: number | null;
  room: string | null;
};

export type SmartHomeIntegration = {
  id: string;
  household_id: string;
  provider: "google_home";
  mode: "home_apis" | "nest_sdm";
  status: "planned" | "needs_auth" | "configured" | "sync_error";
  display_name: string;
  project_id: string | null;
  last_sync_at: string | null;
};

export type SmartHomeDevice = {
  id: string;
  household_id: string;
  integration_id: string;
  provider_device_id: string;
  name: string;
  type: string | null;
  room: string | null;
  traits: Record<string, unknown>;
  state: Record<string, unknown>;
  updated_at: string;
};

export type WishlistItem = {
  id: string;
  household_id: string;
  title: string;
  description: string | null;
  url: string | null;
  image_url: string | null;
  desired_by: string | null;
  category: string | null;
  price_cents: number | null;
  priority: "laag" | "normaal" | "hoog";
  status: "open" | "reserved" | "purchased";
  purchase_mode: "single" | "repeatable";
  purchase_count: number;
  is_public: boolean;
  reserved_by_name: string | null;
  reserved_at: string | null;
  purchased_at: string | null;
  last_purchased_at: string | null;
  created_at: string;
};

export type WishlistShare = {
  id: string;
  household_id: string;
  title: string;
  public_token: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type AppData = {
  household: Household;
  householdPreferences: HouseholdPreferences;
  members: HouseholdMember[];
  householdContacts: HouseholdContact[];
  householdContactMembers?: HouseholdContactMember[];
  householdBirthdays?: HouseholdBirthday[];
  householdInfoItems: HouseholdInfoItem[];
  maintenanceItems: MaintenanceItem[];
  householdNotes: HouseholdNote[];
  householdDocuments: HouseholdDocument[];
  taskIntegrations: TaskIntegration[];
  tasks: Task[];
  shoppingList: ShoppingList | null;
  shoppingItems: ShoppingItem[];
  shoppingProducts: ShoppingProduct[];
  mealPlans: MealPlan[];
  priceObservations: PriceObservation[];
  shoppingScans: ShoppingScan[];
  financeItems: FinanceItem[];
  financeBudgets: FinanceBudget[];
  bankConnections: BankConnection[];
  bankAccounts: BankAccount[];
  bankTransactions: BankTransaction[];
  recurringTransactionRules: RecurringTransactionRule[];
  calendarIntegrations: CalendarIntegration[];
  icsCalendarSubscriptions?: IcsCalendarSubscription[];
  icsCalendarFileImports?: IcsCalendarFileImport[];
  calendarEvents: CalendarEvent[];
  hasHomeAssistantConfig: boolean;
  hasHueConfig: boolean;
  smartHomeIntegrations: SmartHomeIntegration[];
  smartHomeDevices: SmartHomeDevice[];
  wishlistItems: WishlistItem[];
  wishlistShares: WishlistShare[];
};
