"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, CheckSquare, Euro, Home, Play, Power, RotateCcw, ShoppingBasket, Trash2 } from "lucide-react";
import { demoData } from "@/lib/demo-data";
import { memberName, money, shortDate } from "@/lib/format";
import { filterTasks, type TaskFilter } from "@/lib/task-filters";
import type { AppData, CalendarEvent, FinanceItem, PriceObservation, ShoppingItem, ShoppingProduct, Task } from "@/lib/types";

type DemoView = "dashboard" | "taken" | "boodschappen" | "geld" | "agenda" | "home" | "instellingen";
type DemoDevice = {
  entityId: string;
  name: string;
  room: string;
  domain: "light" | "switch" | "scene" | "sensor";
  state: string;
  updatedAt: string;
  readonly?: boolean;
};
type DemoHomeLog = {
  id: string;
  message: string;
  createdAt: string;
};
type DemoHomeState = {
  devices: DemoDevice[];
  logs: DemoHomeLog[];
};

const storageKey = "family-app-demo-v1";
const homeStorageKey = "family-app-demo-home-v1";
const demoHomeState: DemoHomeState = {
  devices: [
    { entityId: "light.woonkamer", name: "Woonkamerlamp", room: "Woonkamer", domain: "light", state: "aan", updatedAt: "Net" },
    { entityId: "switch.koffiezetapparaat", name: "Koffiezetapparaat", room: "Keuken", domain: "switch", state: "uit", updatedAt: "Net" },
    { entityId: "scene.avond", name: "Avondscene", room: "Beneden", domain: "scene", state: "klaar", updatedAt: "Net" },
    { entityId: "sensor.temperatuur", name: "Temperatuur", room: "Woonkamer", domain: "sensor", state: "21,4 °C", updatedAt: "Net", readonly: true },
  ],
  logs: [{ id: "log-1", message: "Demo Home gestart", createdAt: "Net" }],
};

function nextId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeDemoData(raw: string | null): AppData {
  if (!raw) return demoData;

  try {
    const parsed = JSON.parse(raw) as Partial<AppData>;
    return {
      ...demoData,
      ...parsed,
      household: parsed.household ?? demoData.household,
      householdPreferences: parsed.householdPreferences ?? demoData.householdPreferences,
      members: Array.isArray(parsed.members) ? parsed.members : demoData.members,
      householdContacts: Array.isArray(parsed.householdContacts) ? parsed.householdContacts : demoData.householdContacts,
      householdInfoItems: Array.isArray(parsed.householdInfoItems) ? parsed.householdInfoItems : demoData.householdInfoItems,
      maintenanceItems: Array.isArray(parsed.maintenanceItems) ? parsed.maintenanceItems : demoData.maintenanceItems,
      householdNotes: Array.isArray(parsed.householdNotes) ? parsed.householdNotes : demoData.householdNotes,
      householdDocuments: Array.isArray(parsed.householdDocuments) ? parsed.householdDocuments : demoData.householdDocuments,
      tasks: Array.isArray(parsed.tasks) ? parsed.tasks : demoData.tasks,
      shoppingList: parsed.shoppingList ?? demoData.shoppingList,
      shoppingItems: Array.isArray(parsed.shoppingItems) ? parsed.shoppingItems : demoData.shoppingItems,
      shoppingProducts: Array.isArray(parsed.shoppingProducts) ? parsed.shoppingProducts : demoData.shoppingProducts,
      mealPlans: Array.isArray(parsed.mealPlans) ? parsed.mealPlans : demoData.mealPlans,
      priceObservations: Array.isArray(parsed.priceObservations) ? parsed.priceObservations : demoData.priceObservations,
      shoppingScans: Array.isArray(parsed.shoppingScans) ? parsed.shoppingScans : demoData.shoppingScans,
      financeItems: Array.isArray(parsed.financeItems) ? parsed.financeItems : demoData.financeItems,
      financeBudgets: Array.isArray(parsed.financeBudgets) ? parsed.financeBudgets : demoData.financeBudgets,
      bankConnections: Array.isArray(parsed.bankConnections) ? parsed.bankConnections : demoData.bankConnections,
      bankAccounts: Array.isArray(parsed.bankAccounts) ? parsed.bankAccounts : demoData.bankAccounts,
      bankTransactions: Array.isArray(parsed.bankTransactions) ? parsed.bankTransactions : demoData.bankTransactions,
      calendarIntegrations: Array.isArray(parsed.calendarIntegrations) ? parsed.calendarIntegrations : demoData.calendarIntegrations,
      calendarEvents: Array.isArray(parsed.calendarEvents) ? parsed.calendarEvents : demoData.calendarEvents,
      hasHomeAssistantConfig: parsed.hasHomeAssistantConfig ?? demoData.hasHomeAssistantConfig,
      hasHueConfig: parsed.hasHueConfig ?? demoData.hasHueConfig,
      smartHomeIntegrations: Array.isArray(parsed.smartHomeIntegrations) ? parsed.smartHomeIntegrations : demoData.smartHomeIntegrations,
      smartHomeDevices: Array.isArray(parsed.smartHomeDevices) ? parsed.smartHomeDevices : demoData.smartHomeDevices,
      wishlistItems: Array.isArray(parsed.wishlistItems) ? parsed.wishlistItems : demoData.wishlistItems,
      wishlistShares: Array.isArray(parsed.wishlistShares) ? parsed.wishlistShares : demoData.wishlistShares,
    };
  } catch {
    return demoData;
  }
}

function normalizeHomeState(raw: string | null): DemoHomeState {
  if (!raw) return demoHomeState;
  const defaultsByEntity = new Map(demoHomeState.devices.map((device) => [device.entityId, device]));
  const normalizeDevice = (device: DemoDevice): DemoDevice => {
    const defaults = defaultsByEntity.get(device.entityId);
    return {
      ...device,
      room: defaults?.room ?? device.room ?? "Woonkamer",
      updatedAt: device.updatedAt ?? "Net",
    };
  };

  try {
    const parsed = JSON.parse(raw) as Partial<DemoHomeState> | DemoDevice[];
    if (Array.isArray(parsed)) {
      return {
        devices: parsed.map(normalizeDevice),
        logs: demoHomeState.logs,
      };
    }

    if (Array.isArray(parsed.devices)) {
      return {
        devices: parsed.devices.map(normalizeDevice),
        logs: Array.isArray(parsed.logs) ? parsed.logs : demoHomeState.logs,
      };
    }
  } catch {
    return demoHomeState;
  }

  return demoHomeState;
}

export function DemoWorkspace({ view, filter = "open" }: { view: DemoView; filter?: TaskFilter }) {
  const [data, setData] = useState<AppData>(() => {
    if (typeof window === "undefined") return demoData;
    return normalizeDemoData(window.localStorage.getItem(storageKey));
  });
  const [homeState, setHomeState] = useState<DemoHomeState>(() => {
    if (typeof window === "undefined") return demoHomeState;
    return normalizeHomeState(window.localStorage.getItem(homeStorageKey));
  });

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(data));
  }, [data]);

  useEffect(() => {
    window.localStorage.setItem(homeStorageKey, JSON.stringify(homeState));
  }, [homeState]);

  function resetDemo() {
    setData(demoData);
    setHomeState(demoHomeState);
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="container topbar-inner">
          <Link href="/" className="brand" aria-label="Naar dashboard">
            <span className="brand-mark">
              <Home size={19} />
            </span>
            <span>Family App</span>
          </Link>
          <nav className="nav" aria-label="Hoofdnavigatie">
            <Link href="/">Dashboard</Link>
            <Link href="/taken">Taken</Link>
            <Link href="/boodschappen">Boodschappen</Link>
            <Link href="/geld">Geld</Link>
            <Link href="/agenda">Agenda</Link>
            <Link href="/home">Home</Link>
            <Link href="/instellingen">Instellingen</Link>
          </nav>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="status">Demo</span>
            <button className="icon-button" onClick={resetDemo} title="Demo resetten" aria-label="Demo resetten">
              <RotateCcw size={17} />
            </button>
          </div>
        </div>
      </header>
      <main className="main">
        <div className="container">
          {view === "dashboard" && <DemoDashboard data={data} />}
          {view === "taken" && <DemoTasks data={data} setData={setData} filter={filter} />}
          {view === "boodschappen" && <DemoShopping data={data} setData={setData} />}
          {view === "geld" && <DemoFinance data={data} setData={setData} />}
          {view === "agenda" && <DemoCalendar data={data} setData={setData} />}
          {view === "home" && <DemoHome data={data} homeState={homeState} setHomeState={setHomeState} />}
          {view === "instellingen" && <DemoSettings data={data} />}
        </div>
      </main>
    </div>
  );
}

function DemoDashboard({ data }: { data: AppData }) {
  const openTasks = data.tasks.filter((task) => task.status === "open").length;
  const shoppingOpen = data.shoppingItems.filter((item) => !item.checked).length;
  const monthlyTotal = data.financeItems
    .filter((item) => item.frequency === "maandelijks")
    .reduce((sum, item) => sum + item.amount_cents, 0);

  return (
    <>
      <section className="page-title">
        <h1>{data.household.name}</h1>
        <p>Demo-modus: je wijzigingen worden lokaal in deze browser bewaard.</p>
      </section>
      <section className="grid dashboard-grid" style={{ marginTop: 22 }}>
        <SummaryCard icon={<CheckSquare size={20} />} title="Open taken" value={String(openTasks)} href="/taken" />
        <SummaryCard icon={<ShoppingBasket size={20} />} title="Boodschappen" value={String(shoppingOpen)} href="/boodschappen" />
        <SummaryCard icon={<Euro size={20} />} title="Maandlasten" value={money(monthlyTotal)} href="/geld" />
        <SummaryCard icon={<CalendarDays size={20} />} title="Afspraken" value={String(data.calendarEvents.length)} href="/agenda" />
      </section>
      <section className="grid two-col" style={{ marginTop: 22 }}>
        <div className="card">
          <h2>Taken</h2>
          <TaskRows data={data} tasks={data.tasks.slice(0, 4)} />
        </div>
        <div className="card">
          <h2>Boodschappen</h2>
          <ShoppingRows items={data.shoppingItems.slice(0, 4)} />
        </div>
      </section>
    </>
  );
}

function SummaryCard({ icon, title, value, href }: { icon: React.ReactNode; title: string; value: string; href: string }) {
  return (
    <Link href={href} className="card" style={{ color: "inherit", textDecoration: "none" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <h2>{title}</h2>
        {icon}
      </div>
      <div className="metric">{value}</div>
    </Link>
  );
}

function DemoTasks({
  data,
  setData,
  filter,
}: {
  data: AppData;
  setData: React.Dispatch<React.SetStateAction<AppData>>;
  filter: TaskFilter;
}) {
  const tasks = useMemo(() => filterTasks(data.tasks, filter), [data.tasks, filter]);

  function addTask(formData: FormData) {
    const title = String(formData.get("title") ?? "").trim();
    if (!title) return;
    const task: Task = {
      id: nextId("task"),
      household_id: data.household.id,
      title,
      description: null,
      assignee_id: String(formData.get("assignee_id") || "") || null,
      status: "open",
      priority: (String(formData.get("priority") || "normaal") as Task["priority"]) || "normaal",
      due_date: String(formData.get("due_date") || "") || null,
    };
    setData((current) => ({ ...current, tasks: [task, ...current.tasks] }));
  }

  return (
    <section className="grid two-col">
      <div>
        <ModuleHeader title="Taken" count={`${tasks.length} zichtbaar van ${data.tasks.length}`} />
        <div className="nav" aria-label="Taakfilters" style={{ marginBottom: 16 }}>
          <Link href="/taken?filter=open" aria-current={filter === "open" ? "page" : undefined}>
            Open
          </Link>
          <Link href="/taken?filter=vandaag" aria-current={filter === "vandaag" ? "page" : undefined}>
            Vandaag
          </Link>
          <Link href="/taken?filter=alles" aria-current={filter === "alles" ? "page" : undefined}>
            Alles
          </Link>
        </div>
        <TaskRows
          data={data}
          tasks={tasks}
          onToggle={(id) =>
            setData((current) => ({
              ...current,
              tasks: current.tasks.map((task) => (task.id === id ? { ...task, status: task.status === "done" ? "open" : "done" } : task)),
            }))
          }
          onDelete={(id) => setData((current) => ({ ...current, tasks: current.tasks.filter((task) => task.id !== id) }))}
        />
        <div style={{ marginTop: 16 }}>
          <DemoTaskIntegrations data={data} />
        </div>
      </div>
      <form className="card form" action={addTask}>
        <h2>Taak toevoegen</h2>
        <Field label="Titel" name="title" required />
        <div className="field">
          <label htmlFor="demo-task-assignee">Toewijzen</label>
          <select id="demo-task-assignee" name="assignee_id" defaultValue="">
            <option value="">Niet toegewezen</option>
            {data.members.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="demo-task-priority">Prioriteit</label>
          <select id="demo-task-priority" name="priority" defaultValue="normaal">
            <option value="laag">Laag</option>
            <option value="normaal">Normaal</option>
            <option value="hoog">Hoog</option>
          </select>
        </div>
        <Field label="Deadline" name="due_date" type="date" />
        <button className="button primary">Toevoegen</button>
      </form>
    </section>
  );
}

function DemoTaskIntegrations({ data }: { data: AppData }) {
  return (
    <div className="card">
      <h2>Koppelingen</h2>
      <ul className="list">
        {data.taskIntegrations.map((integration) => (
          <li className="list-row" key={integration.id}>
            <div>
              <div className="row-title">{integration.display_name}</div>
              <div className="row-meta">
                {integration.status} · {integration.sync_direction} · {integration.provider === "microsoft_todo" ? "Microsoft Graph OAuth" : "EventKit native bridge"}
              </div>
            </div>
            <span className="status">{integration.provider === "microsoft_todo" ? "Web API" : "Native"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DemoShopping({ data, setData }: { data: AppData; setData: React.Dispatch<React.SetStateAction<AppData>> }) {
  function addItem(formData: FormData) {
    const name = String(formData.get("name") ?? "").trim();
    if (!name || !data.shoppingList) return;
    const quantity = String(formData.get("quantity") || "") || null;
    const category = String(formData.get("category") || "") || null;
    const recurrence = String(formData.get("recurrence") || "none") as ShoppingProduct["recurrence"];
    const price = Number(String(formData.get("price") || "").replace(",", "."));
    const store = String(formData.get("store") || "") || null;
    const existingProduct = data.shoppingProducts.find((product) => product.name.toLowerCase() === name.toLowerCase());
    const product: ShoppingProduct = existingProduct ?? {
      id: nextId("product"),
      household_id: data.household.id,
      name,
      category,
      default_quantity: quantity,
      recurrence,
      purchase_count: 0,
      last_purchased_at: null,
    };
    const item: ShoppingItem = {
      id: nextId("shop"),
      household_id: data.household.id,
      list_id: data.shoppingList.id,
      product_id: product.id,
      name,
      quantity,
      category,
      checked: false,
    };
    const priceObservation: PriceObservation | null = Number.isFinite(price) && price >= 0 && String(formData.get("price") || "").trim()
      ? {
          id: nextId("price"),
          household_id: data.household.id,
          product_id: product.id,
          product_name: name,
          store,
          observed_at: new Date().toISOString(),
          unit_price_cents: null,
          total_price_cents: Math.round(price * 100),
          quantity,
          source: "manual",
        }
      : null;

    setData((current) => ({
      ...current,
      shoppingItems: [item, ...current.shoppingItems],
      shoppingProducts: existingProduct
        ? current.shoppingProducts.map((currentProduct) =>
            currentProduct.id === existingProduct.id
              ? { ...currentProduct, category, default_quantity: quantity, recurrence }
              : currentProduct,
          )
        : [product, ...current.shoppingProducts],
      priceObservations: priceObservation ? [priceObservation, ...current.priceObservations] : current.priceObservations,
    }));
  }

  return (
    <section className="grid two-col">
      <div>
        <ModuleHeader title="Boodschappen" count={`${data.shoppingItems.filter((item) => !item.checked).length} open`} />
        <div className="grid">
          <ShoppingRows
            items={data.shoppingItems}
            onToggle={(id) =>
              setData((current) => {
                const target = current.shoppingItems.find((item) => item.id === id);
                return {
                  ...current,
                  shoppingItems: current.shoppingItems.map((item) => (item.id === id ? { ...item, checked: !item.checked } : item)),
                  shoppingProducts:
                    target?.product_id && !target.checked
                      ? current.shoppingProducts.map((product) =>
                          product.id === target.product_id
                            ? { ...product, purchase_count: product.purchase_count + 1, last_purchased_at: new Date().toISOString() }
                            : product,
                        )
                      : current.shoppingProducts,
                };
              })
            }
            onDelete={(id) => setData((current) => ({ ...current, shoppingItems: current.shoppingItems.filter((item) => item.id !== id) }))}
          />
          <DemoSmartShopping data={data} setData={setData} />
          <DemoPriceHistory data={data} />
        </div>
      </div>
      <div className="grid">
        <form className="card form" action={addItem}>
          <h2>Boodschap toevoegen</h2>
          <Field label="Naam" name="name" required />
          <Field label="Aantal" name="quantity" placeholder="bijv. 2 pakken" />
          <Field label="Categorie" name="category" placeholder="Groente, zuivel, drogist" />
          <div className="field">
            <label htmlFor="demo-recurrence">Herhaling</label>
            <select id="demo-recurrence" name="recurrence" defaultValue="none">
              <option value="none">Niet terugkerend</option>
              <option value="weekly">Wekelijks</option>
              <option value="biweekly">Elke twee weken</option>
              <option value="monthly">Maandelijks</option>
            </select>
          </div>
          <Field label="Prijs" name="price" type="number" min="0" step="0.01" placeholder="Optioneel" />
          <Field label="Winkel" name="store" placeholder="bijv. Albert Heijn" />
          <button className="button primary">Toevoegen</button>
        </form>
        <DemoOcrPanel data={data} setData={setData} />
      </div>
    </section>
  );
}

function DemoSmartShopping({ data, setData }: { data: AppData; setData: React.Dispatch<React.SetStateAction<AppData>> }) {
  const recurring = data.shoppingProducts.filter((product) => product.recurrence !== "none").slice(0, 6);
  const topProducts = [...data.shoppingProducts].sort((a, b) => b.purchase_count - a.purchase_count).slice(0, 6);

  function addRecurring(product: ShoppingProduct) {
    if (!data.shoppingList) return;
    const item: ShoppingItem = {
      id: nextId("shop"),
      household_id: data.household.id,
      list_id: data.shoppingList.id,
      product_id: product.id,
      name: product.name,
      category: product.category,
      quantity: product.default_quantity,
      checked: false,
    };
    setData((current) => ({ ...current, shoppingItems: [item, ...current.shoppingItems] }));
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>Terugkerend</h2>
        <ul className="list">
          {recurring.map((product) => (
            <li className="list-row" key={product.id}>
              <div>
                <div className="row-title">{product.name}</div>
                <div className="row-meta">
                  {product.recurrence} · {product.default_quantity ?? "Geen hoeveelheid"} · {product.purchase_count}x gekocht
                </div>
              </div>
              <button className="button" onClick={() => addRecurring(product)}>
                Toevoegen
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h2>Vaak gekocht</h2>
        <ul className="list">
          {topProducts.map((product) => (
            <li className="list-row" key={product.id}>
              <div>
                <div className="row-title">{product.name}</div>
                <div className="row-meta">
                  {product.purchase_count}x · laatst {shortDate(product.last_purchased_at)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function DemoPriceHistory({ data }: { data: AppData }) {
  return (
    <div className="card">
      <h2>Prijshistorie</h2>
      <ul className="list">
        {data.priceObservations.slice(0, 6).map((price) => (
          <li className="list-row" key={price.id}>
            <div>
              <div className="row-title">{price.product_name}</div>
              <div className="row-meta">
                {price.store ?? "Onbekende winkel"} · {shortDate(price.observed_at)} · {price.source}
              </div>
            </div>
            <span className="status">{money(price.total_price_cents)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DemoOcrPanel({ data, setData }: { data: AppData; setData: React.Dispatch<React.SetStateAction<AppData>> }) {
  function simulateScan() {
    const scan = {
      id: nextId("scan"),
      household_id: data.household.id,
      status: "needs_review" as const,
      source_filename: "demo-bon.jpg",
      extracted_text: "BROOD 2.19\nBANANEN 1.74\nHAVERMELK 1.89",
      created_at: new Date().toISOString(),
    };
    const price: PriceObservation = {
      id: nextId("price"),
      household_id: data.household.id,
      product_id: null,
      product_name: "Brood",
      store: "Demo OCR",
      observed_at: new Date().toISOString(),
      unit_price_cents: 219,
      total_price_cents: 219,
      quantity: "1 stuk",
      source: "ocr",
    };
    setData((current) => ({ ...current, shoppingScans: [scan, ...current.shoppingScans], priceObservations: [price, ...current.priceObservations] }));
  }

  return (
    <div className="card">
      <h2>Foto check</h2>
      <p className="muted">Demo OCR herkent voorbeeldregels uit een bon en zet ze klaar voor review.</p>
      <button className="button primary" onClick={simulateScan}>
        Scan demo-bon
      </button>
      <ul className="list" style={{ marginTop: 12 }}>
        {data.shoppingScans.slice(0, 4).map((scan) => (
          <li className="list-row" key={scan.id}>
            <div>
              <div className="row-title">{scan.source_filename ?? "Scan"}</div>
              <div className="row-meta">{scan.status}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DemoFinance({ data, setData }: { data: AppData; setData: React.Dispatch<React.SetStateAction<AppData>> }) {
  const monthlyTotal = data.financeItems
    .filter((item) => item.frequency === "maandelijks")
    .reduce((sum, item) => sum + item.amount_cents, 0);
  const bankBalance = data.bankAccounts.reduce((sum, account) => sum + (account.balance_cents ?? 0), 0);

  function addItem(formData: FormData) {
    const title = String(formData.get("title") ?? "").trim();
    const amount = Number(String(formData.get("amount") ?? "0").replace(",", "."));
    if (!title || !Number.isFinite(amount) || amount < 0) return;
    const item: FinanceItem = {
      id: nextId("finance"),
      household_id: data.household.id,
      title,
      category: String(formData.get("category") || "Algemeen"),
      amount_cents: Math.round(amount * 100),
      frequency: String(formData.get("frequency") || "maandelijks") as FinanceItem["frequency"],
      due_date: String(formData.get("due_date") || "") || null,
      status: "actief",
    };
    setData((current) => ({ ...current, financeItems: [...current.financeItems, item] }));
  }

  return (
    <section className="grid two-col">
      <div>
        <ModuleHeader title="Geld" count={`Maandlasten ${money(monthlyTotal)}`} />
        <div className="grid">
          <div className="card">
            <h2>Bank</h2>
            <div className="metric">{money(bankBalance)}</div>
            <p className="muted">Demo bunq-saldo over {data.bankAccounts.length} rekeningen</p>
          </div>
          <FinanceRows items={data.financeItems} onDelete={(id) => setData((current) => ({ ...current, financeItems: current.financeItems.filter((item) => item.id !== id) }))} />
          <DemoTransactions data={data} />
        </div>
      </div>
      <form className="card form" action={addItem}>
        <h2>Gelditem toevoegen</h2>
        <Field label="Titel" name="title" required />
        <Field label="Bedrag" name="amount" type="number" min="0" step="0.01" required />
        <Field label="Categorie" name="category" defaultValue="Vaste lasten" />
        <div className="field">
          <label htmlFor="demo-finance-frequency">Frequentie</label>
          <select id="demo-finance-frequency" name="frequency" defaultValue="maandelijks">
            <option value="eenmalig">Eenmalig</option>
            <option value="maandelijks">Maandelijks</option>
            <option value="jaarlijks">Jaarlijks</option>
          </select>
        </div>
        <Field label="Betaaldatum" name="due_date" type="date" />
        <button className="button primary">Toevoegen</button>
      </form>
    </section>
  );
}

function DemoTransactions({ data }: { data: AppData }) {
  return (
    <div className="card">
      <h2>Recente transacties</h2>
      <ul className="list">
        {data.bankTransactions.map((transaction) => (
          <li className="list-row" key={transaction.id}>
            <div className="row-main">
              <div className="row-title">{transaction.description}</div>
              <div className="row-meta">
                {shortDate(transaction.booked_at)} · {transaction.counterparty ?? "Onbekend"} · {transaction.category ?? "Ongecategoriseerd"}
              </div>
            </div>
            <span className="status">{money(transaction.amount_cents)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DemoCalendar({ data, setData }: { data: AppData; setData: React.Dispatch<React.SetStateAction<AppData>> }) {
  function addEvent(formData: FormData) {
    const title = String(formData.get("title") ?? "").trim();
    const startsAt = String(formData.get("starts_at") || "");
    if (!title || !startsAt) return;
    const event: CalendarEvent = {
      id: nextId("event"),
      household_id: data.household.id,
      title,
      starts_at: new Date(startsAt).toISOString(),
      ends_at: null,
      location: String(formData.get("location") || "") || null,
      participant_ids: formData.getAll("participant_ids").filter((item): item is string => typeof item === "string"),
    };
    setData((current) => ({ ...current, calendarEvents: [...current.calendarEvents, event] }));
  }

  return (
    <section className="grid two-col">
      <div>
        <ModuleHeader title="Agenda" count={`${data.calendarEvents.length} afspraken`} />
        <CalendarRows events={data.calendarEvents} onDelete={(id) => setData((current) => ({ ...current, calendarEvents: current.calendarEvents.filter((event) => event.id !== id) }))} />
      </div>
      <div className="grid">
        <div className="card">
          <h2>Agenda-koppelingen</h2>
          <ul className="list">
            {data.calendarIntegrations.map((integration) => (
              <li className="list-row" key={integration.id}>
                <div>
                  <div className="row-title">{integration.display_name}</div>
                  <div className="row-meta">
                    {integration.account_email ?? "Outlook.com"} · {integration.status} · laatst {shortDate(integration.last_sync_at)}
                  </div>
                </div>
                <span className="status">Outlook</span>
              </li>
            ))}
          </ul>
          <p className="muted" style={{ marginBottom: 0 }}>
            In productie koppelt elk gezinslid zijn eigen Outlook.com-account via Microsoft OAuth. Na sync staat alles samen in deze agenda.
          </p>
        </div>
        <form className="card form" action={addEvent}>
          <h2>Afspraak toevoegen</h2>
          <Field label="Titel" name="title" required />
          <Field label="Start" name="starts_at" type="datetime-local" required />
          <Field label="Locatie" name="location" />
          <div className="field">
            <label htmlFor="demo-event-members">Gezinsleden</label>
            <select id="demo-event-members" name="participant_ids" multiple>
              {data.members.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}
                </option>
              ))}
            </select>
          </div>
          <button className="button primary">Toevoegen</button>
        </form>
      </div>
    </section>
  );
}

function DemoHome({
  data,
  homeState,
  setHomeState,
}: {
  data: AppData;
  homeState: DemoHomeState;
  setHomeState: React.Dispatch<React.SetStateAction<DemoHomeState>>;
}) {
  const [room, setRoom] = useState("Alle ruimtes");
  const rooms = ["Alle ruimtes", ...Array.from(new Set(homeState.devices.map((device) => device.room)))];
  const visibleDevices = room === "Alle ruimtes" ? homeState.devices : homeState.devices.filter((device) => device.room === room);
  const activeDevices = homeState.devices.filter((device) => device.state === "aan" || device.state === "actief").length;

  function runDevice(device: DemoDevice) {
    if (device.readonly) return;
    const nextState = device.domain === "scene" ? "actief" : device.state === "aan" ? "uit" : "aan";
    const message = `${device.name} ${device.domain === "scene" ? "gestart" : `naar ${nextState} gezet`}`;
    setHomeState((current) => ({
      devices: current.devices.map((item) =>
        item.entityId === device.entityId
          ? {
              ...item,
              state: nextState,
              updatedAt: "Net",
            }
          : item,
      ),
      logs: [{ id: nextId("log"), message, createdAt: "Net" }, ...current.logs].slice(0, 6),
    }));
  }

  return (
    <section className="grid two-col">
      <div>
        <ModuleHeader title="Home" count={`${activeDevices} apparaten of scènes actief`} />
        <div className="nav" aria-label="Ruimtefilter" style={{ marginBottom: 16 }}>
          {rooms.map((item) => (
            <button
              className="button"
              key={item}
              onClick={() => setRoom(item)}
              aria-pressed={room === item}
              style={room === item ? { borderColor: "var(--primary)", color: "var(--primary-strong)" } : undefined}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="card">
          <h2>Apparaten</h2>
          <ul className="list">
            {visibleDevices.map((device) => (
              <li className="list-row" key={device.entityId}>
                <div>
                  <div className="row-title">{device.name}</div>
                  <div className="row-meta">
                    {device.room} · {device.entityId} · {device.state} · {device.updatedAt}
                  </div>
                </div>
                {device.readonly ? (
                  <span className="status">Alleen lezen</span>
                ) : (
                  <button className="button" onClick={() => runDevice(device)}>
                    {device.domain === "scene" ? <Play size={17} /> : <Power size={17} />}
                    {device.domain === "scene" ? "Start" : device.state === "aan" ? "Zet uit" : "Zet aan"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="grid">
        <div className="card">
          <h2>Actielog</h2>
          <ul className="list">
            {homeState.logs.map((log) => (
              <li className="list-row" key={log.id}>
                <div>
                  <div className="row-title">{log.message}</div>
                  <div className="row-meta">{log.createdAt}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h2>Integratiepad</h2>
          <p className="muted">
            In productie gebruikt deze module server-side koppelingen voor Home Assistant, Hue en Google Home. Tokens blijven op de
            server en apparaten worden per huishouden gesynchroniseerd.
          </p>
        </div>
        <div className="card">
          <h2>Google Home</h2>
          <ul className="list">
            {data.smartHomeIntegrations
              .filter((integration) => integration.provider === "google_home")
              .map((integration) => (
                <li className="list-row" key={integration.id}>
                  <div>
                    <div className="row-title">{integration.display_name}</div>
                    <div className="row-meta">
                      {integration.mode === "nest_sdm" ? "Nest SDM" : "Home APIs"} · {integration.status}
                    </div>
                  </div>
                  <span className="status">OAuth nodig</span>
                </li>
              ))}
          </ul>
          <p className="muted" style={{ marginBottom: 0 }}>
            Nest SDM is in productie te autoriseren via Google OAuth en synchroniseert ondersteunde Nest-apparaten server-side. Brede
            Google Home APIs blijven voorbereid voor een latere mobiele platformlaag.
          </p>
        </div>
      </div>
    </section>
  );
}

function DemoSettings({ data }: { data: AppData }) {
  return (
    <section className="grid two-col">
      <div className="grid">
        <div>
          <h1>Instellingen</h1>
          <p className="muted">Demo-data staat lokaal in je browser. Reset via de knop rechtsboven.</p>
        </div>
        <div className="card">
          <h2>Gezinsleden</h2>
          <ul className="list">
            {data.members.map((member) => (
              <li className="list-row" key={member.user_id}>
                <div>
                  <div className="row-title">{member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"}</div>
                  <div className="row-meta">{member.role}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="grid">
        <div className="card">
          <h2>Philips Hue</h2>
          <p className="muted">
            Eerste live smart-home koppeling wordt direct Hue Bridge: bridge URL plus app key. Google Home blijft later interessant als
            overkoepelende integratie.
          </p>
        </div>
        <div className="card">
          <h2>Google Home</h2>
          <p className="muted">
            Nest SDM gebruikt OAuth en een Device Access project om ondersteunde Nest-apparaten te synchroniseren. Google Home APIs blijven
            voorbereid voor een latere mobiele platformlaag.
          </p>
        </div>
        <div className="card">
          <h2>Outlook agenda</h2>
          <p className="muted">
            Elk gezinslid koppelt zijn eigen Outlook.com-account. De app haalt afspraken via Microsoft Graph calendarView op en toont ze
            samen met lokale gezinsafspraken.
          </p>
        </div>
        <div className="card">
          <h2>PostgreSQL activeren</h2>
          <p className="muted">
            Zet `DATABASE_URL` in `.env.local` en start daarna de app opnieuw.
          </p>
        </div>
      </div>
    </section>
  );
}

function ModuleHeader({ title, count }: { title: string; count: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h1 style={{ margin: 0 }}>{title}</h1>
      <p className="muted" style={{ margin: "6px 0 0" }}>
        {count}
      </p>
    </div>
  );
}

function Field({
  label,
  name,
  type = "text",
  ...props
}: {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  placeholder?: string;
  defaultValue?: string;
  min?: string;
  step?: string;
}) {
  const id = `demo-${name}`;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} name={name} type={type} {...props} />
    </div>
  );
}

function TaskRows({
  data,
  tasks,
  onToggle,
  onDelete,
}: {
  data: AppData;
  tasks: Task[];
  onToggle?: (id: string) => void;
  onDelete?: (id: string) => void;
}) {
  return (
    <ul className="list">
      {tasks.length === 0 && <li className="muted">Nog geen taken.</li>}
      {tasks.map((task) => (
        <li className="list-row" key={task.id}>
          <div className="row-main">
            <div className="row-title" style={{ textDecoration: task.status === "done" ? "line-through" : undefined }}>{task.title}</div>
            <div className="row-meta">
              {memberName(task.assignee_id, data.members)} · {task.priority} · {shortDate(task.due_date)}
            </div>
          </div>
          {onToggle && onDelete && (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="icon-button" onClick={() => onToggle(task.id)} title="Status wisselen" aria-label="Status wisselen">
                <Check size={17} />
              </button>
              <button className="icon-button" onClick={() => onDelete(task.id)} title="Verwijderen" aria-label="Verwijderen">
                <Trash2 size={17} />
              </button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function ShoppingRows({
  items,
  onToggle,
  onDelete,
}: {
  items: ShoppingItem[];
  onToggle?: (id: string) => void;
  onDelete?: (id: string) => void;
}) {
  return (
    <ul className="list">
      {items.length === 0 && <li className="muted">Nog geen boodschappen.</li>}
      {items.map((item) => (
        <li className="list-row" key={item.id}>
          <div className="row-main">
            <div className="row-title" style={{ textDecoration: item.checked ? "line-through" : undefined }}>{item.name}</div>
            <div className="row-meta">{[item.quantity, item.category].filter(Boolean).join(" · ") || "Geen details"}</div>
          </div>
          {onToggle && onDelete && (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="icon-button" onClick={() => onToggle(item.id)} title="Afvinken" aria-label="Afvinken">
                <Check size={17} />
              </button>
              <button className="icon-button" onClick={() => onDelete(item.id)} title="Verwijderen" aria-label="Verwijderen">
                <Trash2 size={17} />
              </button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function FinanceRows({ items, onDelete }: { items: FinanceItem[]; onDelete: (id: string) => void }) {
  return (
    <ul className="list">
      {items.length === 0 && <li className="muted">Nog geen gelditems.</li>}
      {items.map((item) => (
        <li className="list-row" key={item.id}>
          <div className="row-main">
            <div className="row-title">{item.title}</div>
            <div className="row-meta">
              {item.category} · {item.frequency} · {shortDate(item.due_date)}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="status">{money(item.amount_cents)}</span>
            <button className="icon-button" onClick={() => onDelete(item.id)} title="Verwijderen" aria-label="Verwijderen">
              <Trash2 size={17} />
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function CalendarRows({ events, onDelete }: { events: CalendarEvent[]; onDelete: (id: string) => void }) {
  return (
    <ul className="list">
      {events.length === 0 && <li className="muted">Nog geen afspraken.</li>}
      {events.map((event) => (
        <li className="list-row" key={event.id}>
          <div className="row-main">
            <div className="row-title">{event.title}</div>
            <div className="row-meta">
              {shortDate(event.starts_at)} · {event.location || "Geen locatie"} ·{" "}
              {!event.source_provider
                ? "Gezin"
                : event.external_calendar_name ?? (event.source_provider === "ics" ? "ICS agenda" : "Outlook")}
            </div>
          </div>
          {event.source_provider ? (
            <span className="status">Gesynchroniseerd</span>
          ) : (
            <button className="icon-button" onClick={() => onDelete(event.id)} title="Verwijderen" aria-label="Verwijderen">
              <Trash2 size={17} />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
