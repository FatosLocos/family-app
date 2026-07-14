import { redirect } from "next/navigation";
import Link from "next/link";
import { ChefHat, CreditCard, ReceiptText, Repeat2, ScanText, ShoppingBasket, Trash2, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { addWeekMealIngredientsToShopping, clearCheckedShoppingItems } from "@/app/actions";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { MealPlanForm, ShoppingForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { ModuleLayout } from "@/components/module-layout";
import { MealPlanList, PriceHistoryPanel, ShoppingListView, ShoppingPriceComparisonPanel, ShoppingScansPanel, SmartShoppingPanel } from "@/components/module-lists";
import { getAppData, getUser } from "@/lib/local-data";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { money, shortDate } from "@/lib/format";
import { buildMealPlanningInsight, mealTypeLabel, splitIngredients } from "@/lib/meal-planning";
import type { AppData, BankTransaction, PriceObservation, ShoppingItem, ShoppingProduct } from "@/lib/types";

export const dynamic = "force-dynamic";

type ShoppingTab = "lijst" | "prijzen" | "maaltijden" | "inzicht";

const shoppingTabs: Array<{ id: ShoppingTab; label: string; href: string; detail: string }> = [
  { id: "lijst", label: "Lijst", href: "/boodschappen", detail: "Open items en terugkerende producten" },
  { id: "prijzen", label: "Prijzen", href: "/boodschappen?tab=prijzen", detail: "Supermarktvergelijking en historie" },
  { id: "maaltijden", label: "Maaltijden", href: "/boodschappen?tab=maaltijden", detail: "Weekmenu met ingredienten" },
  { id: "inzicht", label: "Inzicht", href: "/boodschappen?tab=inzicht", detail: "Bonnen, afschrijvingen en echte prijzen" },
];

export default async function ShoppingPage({ searchParams }: { searchParams?: Promise<{ tab?: string | string[] }> }) {
  const activeTab = normalizeShoppingTab((await searchParams)?.tab);
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <ShoppingContent data={await getLocalAppData()} activeTab={activeTab} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="boodschappen" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <ShoppingContent data={data} activeTab={activeTab} />;
}

function ShoppingContent({ data, activeTab, demo = false }: { data: AppData; activeTab: ShoppingTab; demo?: boolean }) {
  const openItems = data.shoppingItems.filter((item) => !item.checked);
  const dueProducts = getRecurringDue(data.shoppingProducts);
  const latestPrices = getLatestPrices(data.priceObservations);
  const pricedItems = openItems.filter((item) => latestPrices.has(normalizeName(item.name)));
  const estimatedTotal = openItems.reduce((sum, item) => sum + (latestPrices.get(normalizeName(item.name))?.total_price_cents ?? 0), 0);
  const reviewScans = data.shoppingScans.filter((scan) => scan.status === "needs_review" || scan.status === "failed");
  const today = new Date().toISOString().slice(0, 10);
  const mealInsight = buildMealPlanningInsight(data, today);

  return (
    <AppShell demo={demo}>
      <section className="shopping-hub">
        <CompactModuleHeader
          eyebrow="Hoofdcategorie"
          title="Boodschappen"
          stats={[
            { label: "open", value: openItems.length },
            { label: "terugkerend", value: dueProducts.length },
            { label: "richtprijs", value: money(estimatedTotal) },
            { label: "met prijs", value: `${pricedItems.length}/${openItems.length || 0}` },
            { label: "scans", value: reviewScans.length },
          ]}
        >
          Lijst, prijzen, maaltijden en bonnen bij elkaar zodat boodschappen straks ook aan echte rekeningafschrijvingen gekoppeld kunnen worden.
        </CompactModuleHeader>

        <nav className="shopping-tabs" aria-label="Boodschappen onderdelen">
          {shoppingTabs.map((tab) => (
            <Link className={activeTab === tab.id ? "active" : undefined} href={tab.href} aria-current={activeTab === tab.id ? "page" : undefined} key={tab.id}>
              <span>{tab.label}</span>
              <small>{tab.detail}</small>
            </Link>
          ))}
        </nav>

        {activeTab === "lijst" && (
          <ModuleLayout
            asideLabel="Boodschappenacties"
            aside={<>{demo ? <DemoPanel /> : <ModuleSubmenu title="Boodschap toevoegen" detail="Product snel op de gedeelde lijst zetten"><ShoppingForm listId={data.shoppingList?.id ?? null} defaultStore={data.householdPreferences.default_shopping_store} /></ModuleSubmenu>}<ShoppingScansPanel data={data} /></>}
          >
            <div className="grid">
              <ShoppingListView data={data} readOnly={demo} />
              <SmartShoppingPanel data={data} />
            </div>
          </ModuleLayout>
        )}

        {activeTab === "prijzen" && (
          <ModuleLayout asideLabel="Prijsinformatie" aside={<><PriceTabInfo /><ShoppingScansPanel data={data} /></>}>
            <div className="grid">
              <ShoppingPriceComparisonPanel data={data} />
              <PriceHistoryPanel data={data} />
            </div>
          </ModuleLayout>
        )}

        {activeTab === "maaltijden" && (
          <ModuleLayout
            asideLabel="Maaltijdacties"
            aside={<>{demo ? <DemoPanel /> : <ModuleSubmenu title="Maaltijd plannen" detail="Maaltijd, datum en ingredienten vastleggen"><MealPlanForm /></ModuleSubmenu>}<MealIngredientsPanel missingIngredients={mealInsight.missingIngredients} /></>}
          >
            <div className="grid">
              <MealPlanList data={data} readOnly={demo} />
              <MealControlPanel data={data} today={today} />
            </div>
          </ModuleLayout>
        )}

        {activeTab === "inzicht" && (
          <ModuleLayout asideLabel="Boodschappeninzichten" aside={<><ShoppingScansPanel data={data} /><PriceHistoryPanel data={data} /></>}>
            <div className="grid">
              <ShoppingControlPanel data={data} />
              <ReceiptBankInsightPanel data={data} />
            </div>
          </ModuleLayout>
        )}
      </section>
    </AppShell>
  );
}

function ShoppingControlPanel({ data }: { data: AppData }) {
  const openItems = data.shoppingItems.filter((item) => !item.checked);
  const checkedItems = data.shoppingItems.filter((item) => item.checked);
  const dueProducts = getRecurringDue(data.shoppingProducts);
  const latestPrices = getLatestPrices(data.priceObservations);
  const pricedItems = openItems.filter((item) => latestPrices.has(normalizeName(item.name)));
  const estimatedTotal = openItems.reduce((sum, item) => sum + (latestPrices.get(normalizeName(item.name))?.total_price_cents ?? 0), 0);
  const reviewScans = data.shoppingScans.filter((scan) => scan.status === "needs_review" || scan.status === "failed");
  const categoryCoverage = openItems.length === 0 ? 100 : Math.round((openItems.filter((item) => item.category).length / openItems.length) * 100);
  const priceCoverage = openItems.length === 0 ? 100 : Math.round((pricedItems.length / openItems.length) * 100);
  const defaultStore = data.householdPreferences.default_shopping_store?.trim() || "Geen standaardwinkel";
  const nextAction = dueProducts[0]
    ? {
        title: `${dueProducts[0].name} is weer logisch om te kopen`,
        detail: `${recurrenceLabel(dueProducts[0].recurrence)} · laatst ${shortDate(dueProducts[0].last_purchased_at)}`,
        href: "/routines",
      }
    : reviewScans[0]
      ? {
          title: "Scan vraagt controle",
          detail: `${reviewScans[0].source_filename ?? "Bon of productfoto"} · ${reviewScans[0].status === "failed" ? "mislukt" : "review nodig"}`,
          href: "/boodschappen",
        }
      : openItems.find((item) => !item.category)
        ? {
            title: `${openItems.find((item) => !item.category)?.name} mist categorie`,
            detail: "Categorieen maken routes, winkels en prijsinzichten later slimmer.",
            href: "/boodschappen",
          }
        : {
            title: openItems.length === 0 ? "Lijst is leeg" : "Lijst is klaar voor de winkel",
            detail: openItems.length === 0 ? "Voeg losse producten of maaltijdingredienten toe." : `${openItems.length} open items met ${priceCoverage}% prijsdekking.`,
            href: "/boodschappen?tab=maaltijden",
          };

  return (
    <section className="shopping-control card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Regie</span>
          <h2>Boodschappenregie</h2>
          <p className="muted">Open lijst, terugkerende producten, bonnen en prijsdekking bij elkaar.</p>
        </div>
        <span className={dueProducts.length + reviewScans.length > 0 ? "status accent" : "status"}>
          {dueProducts.length + reviewScans.length} aandacht
        </span>
      </div>
      <div className="shopping-control-grid">
        <ShoppingMetric icon={<ShoppingBasket size={17} />} label="Open" value={openItems.length} detail={`${checkedItems.length} afgevinkt`} />
        <ShoppingMetric icon={<Repeat2 size={17} />} label="Terugkerend" value={dueProducts.length} detail="Producten die weer logisch zijn" />
        <ShoppingMetric icon={<TrendingUp size={17} />} label="Schatting" value={money(estimatedTotal)} detail={`${pricedItems.length}/${openItems.length || 0} items met prijs`} />
        <ShoppingMetric icon={<ScanText size={17} />} label="Scans" value={reviewScans.length} detail={`${data.shoppingScans.length} totaal geregistreerd`} />
      </div>
      <div className="shopping-progress-grid">
        <ShoppingProgress label="Categorieen" value={categoryCoverage} />
        <ShoppingProgress label="Prijsdekking" value={priceCoverage} />
      </div>
      <div className="shopping-next-row">
        <div>
          <strong>{nextAction.title}</strong>
          <p className="muted">{nextAction.detail}</p>
        </div>
        <div className="shopping-action-stack">
          <span className="status">{defaultStore}</span>
          {checkedItems.length > 0 && (
            <form action={clearCheckedShoppingItems}>
              <button className="button" title="Afgevinkte boodschappen verwijderen">
                <Trash2 size={17} /> {checkedItems.length} opruimen
              </button>
            </form>
          )}
          <Link className="button" href={nextAction.href}>Open actie</Link>
        </div>
      </div>
      {checkedItems.length > 0 && (
        <div className="shopping-cleanup-note">
          <Trash2 size={16} />
          <span>{checkedItems.length} afgevinkte boodschap{checkedItems.length === 1 ? "" : "pen"} staan nog in de lijst. Ruim ze op zodra de boodschappen verwerkt zijn.</span>
        </div>
      )}
      <div className="shopping-tag-row">
        {dueProducts.slice(0, 5).map((product) => (
          <span className="status" key={product.id}>{product.name}: {recurrenceLabel(product.recurrence)}</span>
        ))}
        {dueProducts.length === 0 && <span className="muted">Geen terugkerende producten die nu aandacht vragen.</span>}
      </div>
    </section>
  );
}

function ShoppingMetric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="shopping-metric">
      <span className="shopping-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function ShoppingProgress({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="shopping-progress-head">
        <span>{label}</span>
        <strong>{value}%</strong>
      </div>
      <div className="progress-track" aria-label={`${label} ${value}%`}>
        <span className={value < 50 ? "progress-fill warning" : "progress-fill"} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function MealControlPanel({ data, today }: { data: AppData; today: string }) {
  const insight = buildMealPlanningInsight(data, today);

  return (
    <section className="meal-control card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Eetplanning</span>
          <h2>Van weekmenu naar boodschappen</h2>
          <p className="muted">Check of eten gepland is en welke ingredienten nog niet op de lijst staan.</p>
        </div>
        <span className="summary-icon">
          <ChefHat size={18} />
        </span>
      </div>
      <div className="meal-control-grid">
        <MealMetric icon={<ChefHat size={17} />} label="Deze week" value={insight.weekMeals.length} detail={`${insight.dinnerCoverage}/7 avonden gepland`} />
        <MealMetric icon={<ShoppingBasket size={17} />} label="Ingrediënten" value={insight.ingredientCount} detail="Uit komende maaltijden" />
        <MealMetric icon={<ShoppingBasket size={17} />} label="Nog niet op lijst" value={insight.missingIngredients.length} detail={`${insight.openShopping} open boodschappen`} />
        <MealMetric icon={<ChefHat size={17} />} label="Volgende" value={insight.nextMeal ? shortDate(insight.nextMeal.planned_date) : "Geen"} detail={insight.nextMeal?.title ?? "Plan je volgende maaltijd"} />
      </div>
      <div className="meal-readiness">
        <div>
          <strong>Weekmenu op orde</strong>
          <span>{insight.score}/{insight.totalChecks} punten</span>
        </div>
        <div className="setup-bar" aria-hidden="true">
          <span style={{ width: `${insight.percent}%` }} />
        </div>
      </div>
      <div className="meal-next-row">
        <div>
          <strong>{insight.nextMeal ? insight.nextMeal.title : insight.nextAction.title}</strong>
          <p className="muted">
            {insight.nextMeal
              ? `${mealTypeLabel(insight.nextMeal.meal_type)} · ${splitIngredients(insight.nextMeal.ingredients).length} ingredienten`
              : insight.nextAction.detail}
          </p>
          <div className="tag-list">
            {insight.missingIngredients.slice(0, 8).map((ingredient) => (
              <span className="tag" key={ingredient}>{ingredient}</span>
            ))}
            {insight.missingIngredients.length === 0 && <span className="muted">Geen ontbrekende ingredienten gevonden.</span>}
          </div>
        </div>
        <div className="meal-action-stack">
          {insight.missingIngredients.length > 0 && (
            <form action={addWeekMealIngredientsToShopping}>
              <button className="button primary">
                <ShoppingBasket size={17} /> {insight.missingIngredients.length} naar lijst
              </button>
            </form>
          )}
          <Link className="button" href="/week">Week bekijken</Link>
        </div>
      </div>
    </section>
  );
}

function MealMetric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="meal-metric">
      <span className="meal-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function MealIngredientsPanel({ missingIngredients }: { missingIngredients: string[] }) {
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Ingrediënten naar lijst</h2>
          <p className="muted">Ontbrekende ingredienten uit komende maaltijden.</p>
        </div>
        <span className="status">{missingIngredients.length}</span>
      </div>
      <div className="tag-list">
        {missingIngredients.slice(0, 14).map((ingredient) => (
          <span className="tag" key={ingredient}>{ingredient}</span>
        ))}
        {missingIngredients.length === 0 && <span className="empty-state">Alles uit je weekmenu staat al op de boodschappenlijst.</span>}
      </div>
    </div>
  );
}

function PriceTabInfo() {
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>Prijsvergelijking</h2>
          <p className="muted">De lijst gebruikt dezelfde open boodschappen, maar toont ze als supermarktgrid.</p>
        </div>
        <span className="summary-icon">
          <TrendingUp size={18} />
        </span>
      </div>
      <ul className="insight-list">
        <li>
          <strong>Productlink per cel</strong>
          <span>Het externe icoon opent de gevonden supermarktpagina als de bron die URL levert.</span>
        </li>
        <li>
          <strong>Bonnen blijven brondata</strong>
          <span>OCR-prijzen en handmatige prijzen blijven zichtbaar in de historie en worden straks met afschrijvingen vergeleken.</span>
        </li>
      </ul>
    </div>
  );
}

function ReceiptBankInsightPanel({ data }: { data: AppData }) {
  const groceryTransactions = getGroceryTransactions(data.bankTransactions);
  const transactionTotal = groceryTransactions.reduce((sum, transaction) => sum + Math.abs(transaction.amount_cents), 0);
  const receiptPrices = data.priceObservations.filter((price) => price.source === "ocr" || price.source === "bank");
  const receiptTotal = receiptPrices.reduce((sum, price) => sum + price.total_price_cents, 0);
  const unmatchedScans = data.shoppingScans.filter((scan) => scan.status === "needs_review" || scan.status === "failed");
  const difference = transactionTotal > 0 && receiptTotal > 0 ? receiptTotal - transactionTotal : null;

  return (
    <section className="card receipt-insight">
      <div className="section-head">
        <div>
          <span className="eyebrow">Bonnen en bank</span>
          <h2>Werkelijke prijscontrole</h2>
          <p className="muted">Voorbereid om bonregels aan de specifieke rekeningafschrijving te koppelen en met de verwachte prijs te vergelijken.</p>
        </div>
        <span className="summary-icon">
          <ReceiptText size={18} />
        </span>
      </div>
      <div className="receipt-insight-grid">
        <ShoppingMetric icon={<ReceiptText size={17} />} label="Bonprijzen" value={money(receiptTotal)} detail={`${receiptPrices.length} regels uit bon/bank`} />
        <ShoppingMetric icon={<CreditCard size={17} />} label="Afschrijvingen" value={money(transactionTotal)} detail={`${groceryTransactions.length} mogelijke transacties`} />
        <ShoppingMetric icon={<ScanText size={17} />} label="Te reviewen" value={unmatchedScans.length} detail="Bonnen die nog aandacht vragen" />
      </div>
      <div className="receipt-match-row">
        <div>
          <strong>{difference === null ? "Koppeling nog niet compleet" : `Verschil ${money(difference)}`}</strong>
          <p className="muted">
            {difference === null
              ? "Zodra bonregels en banktransacties samen beschikbaar zijn, toont dit paneel het verschil tussen kassabon, bankafschrijving en verwachte supermarktprijzen."
              : "Positief betekent dat de bonregels hoger zijn dan de gekoppelde afschrijving; negatief betekent lager."}
          </p>
        </div>
        <span className={difference === null || Math.abs(difference) === 0 ? "status" : "status accent"}>
          {difference === null ? "Voorbereid" : Math.abs(difference) === 0 ? "Match" : "Controle"}
        </span>
      </div>
      <ul className="insight-list">
        {groceryTransactions.slice(0, 4).map((transaction) => (
          <li key={transaction.id}>
            <strong>{transaction.description}</strong>
            <span>{shortDate(transaction.booked_at)} · {money(Math.abs(transaction.amount_cents))}</span>
          </li>
        ))}
        {groceryTransactions.length === 0 && (
          <li>
            <strong>Nog geen supermarkt-afschrijvingen herkend</strong>
            <span>Koppel bankdata of categoriseer transacties als boodschappen om hier matches te zien.</span>
          </li>
        )}
      </ul>
    </section>
  );
}

function normalizeShoppingTab(value: string | string[] | undefined): ShoppingTab {
  const tab = Array.isArray(value) ? value[0] : value;
  if (tab === "prijzen" || tab === "maaltijden" || tab === "inzicht") return tab;
  return "lijst";
}

function getGroceryTransactions(transactions: BankTransaction[]) {
  const storeNames = ["albert heijn", "ah ", "jumbo", "lidl", "kaufland", "plus", "aldi", "coop", "dirk", "boodschappen", "supermarkt"];
  return transactions
    .filter((transaction) => {
      const haystack = `${transaction.description} ${transaction.counterparty ?? ""} ${transaction.category ?? ""}`.toLowerCase();
      return storeNames.some((store) => haystack.includes(store));
    })
    .sort((a, b) => new Date(b.booked_at).getTime() - new Date(a.booked_at).getTime());
}

function getRecurringDue(products: ShoppingProduct[]) {
  const now = new Date();
  const intervals: Record<ShoppingProduct["recurrence"], number> = { none: 0, weekly: 7, biweekly: 14, monthly: 30 };
  return products
    .filter((product) => {
      const interval = intervals[product.recurrence];
      if (!interval) return false;
      if (!product.last_purchased_at) return true;
      return daysBetween(new Date(product.last_purchased_at), now) >= interval;
    })
    .sort((a, b) => recurrenceUrgency(b) - recurrenceUrgency(a));
}

function getLatestPrices(prices: PriceObservation[]) {
  return prices.reduce<Map<string, PriceObservation>>((latest, price) => {
    const key = normalizeName(price.product_name);
    const current = latest.get(key);
    if (!current || price.observed_at > current.observed_at) latest.set(key, price);
    return latest;
  }, new Map());
}

function recurrenceUrgency(product: ShoppingProduct) {
  if (!product.last_purchased_at) return 999;
  return daysBetween(new Date(product.last_purchased_at), new Date());
}

function daysBetween(from: Date, to: Date) {
  return Math.floor((to.getTime() - from.getTime()) / 86_400_000);
}

function recurrenceLabel(recurrence: ShoppingProduct["recurrence"]) {
  if (recurrence === "weekly") return "Wekelijks";
  if (recurrence === "biweekly") return "Elke twee weken";
  if (recurrence === "monthly") return "Maandelijks";
  return "Niet terugkerend";
}

function normalizeName(value: ShoppingItem["name"]) {
  return value.trim().toLowerCase();
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Configureer PostgreSQL om de boodschappenlijst echt te beheren.</p>
    </div>
  );
}
