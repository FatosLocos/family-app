import { redirect } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, Banknote, CalendarClock, PiggyBank, ReceiptText, TrendingDown, TrendingUp, WalletCards } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { DemoWorkspace } from "@/components/demo-workspace";
import { AbnAmroStatementUploadForm, BunqConnectionForm, FinanceBudgetForm, FinanceForm } from "@/components/forms";
import { ModuleSubmenu } from "@/components/module-submenu";
import { ModuleLayout } from "@/components/module-layout";
import { BankAccountsList, BankOverview, BankTransactionsList, FinanceBudgetOverview, FinanceList, RecurringCostsPanel } from "@/components/module-lists";
import { getAppData, getUser } from "@/lib/local-data";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { demoData } from "@/lib/demo-data";
import { buildFinanceDashboardInsight } from "@/lib/finance-insights";
import { money, shortDate } from "@/lib/format";
import type { AppData } from "@/lib/types";

export const dynamic = "force-dynamic";

type TransactionFilters = {
  q: string;
  provider: string;
  account: string;
};

type FinanceTab = "overzicht" | "planning";

export default async function FinancePage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const params = (await searchParams) ?? {};
  const importSummary = buildImportSummary(params);
  const transactionFilters = buildTransactionFilters(params);
  const activeTab = buildFinanceTab(params);
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <FinanceContent data={await getLocalAppData()} importSummary={importSummary} transactionFilters={transactionFilters} activeTab={activeTab} />;
  }
  if (!hasLocalDatabaseEnv()) return <DemoWorkspace view="geld" />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <FinanceContent data={data} importSummary={importSummary} transactionFilters={transactionFilters} activeTab={activeTab} />;
}

function FinanceContent({
  data,
  demo = false,
  importSummary,
  transactionFilters,
  activeTab,
}: {
  data: typeof demoData;
  demo?: boolean;
  importSummary?: string | null;
  transactionFilters: TransactionFilters;
  activeTab: FinanceTab;
}) {
  const monthlyTotal = data.financeItems
    .filter((item) => item.frequency === "maandelijks" && item.status !== "betaald")
    .reduce((sum, item) => sum + item.amount_cents, 0);
  const filteredTransactions = filterBankTransactions(data as AppData, transactionFilters);

  return (
    <AppShell demo={demo}>
      <ModuleLayout
        asideLabel="Geldacties"
        aside={demo ? <DemoPanel /> : <><ModuleSubmenu title="Betaalmoment toevoegen" detail="Vaste last, abonnement of geplande betaling"><FinanceForm /></ModuleSubmenu><ModuleSubmenu title="Budget toevoegen" detail="Maandlimiet en waarschuwingsgrens instellen"><FinanceBudgetForm /></ModuleSubmenu><ModuleSubmenu title="Bank koppelen" detail="Bunq-koppeling of sandbox voorbereiden"><BunqConnectionForm /></ModuleSubmenu><ModuleSubmenu title="Afschrift importeren" detail="ABN AMRO Excel/CSV handmatig toevoegen"><AbnAmroStatementUploadForm /></ModuleSubmenu><BankAccountsList data={data} /></>}
      >
        <div className="grid">
          <CompactModuleHeader
            eyebrow="Planning"
            title="Geld"
            stats={[
              { label: "maandelijks", value: money(monthlyTotal) },
              { label: "rekeningen", value: data.bankAccounts.length },
              { label: "transacties", value: data.bankTransactions.length },
            ]}
          >
            Bankrekeningen, betaalmomenten, budgetten en terugkerende patronen samen beheren.
          </CompactModuleHeader>
          <FinanceTabs activeTab={activeTab} />
          <div className="grid">
            {importSummary && <p className="status accent">{importSummary}</p>}
            {activeTab === "overzicht" ? (
              <>
                <FinanceControlPanel data={data} />
                <BankOverview data={data} />
                <FinanceList data={data} readOnly={demo} />
                <TransactionFilterPanel data={data as AppData} filters={transactionFilters} resultCount={filteredTransactions.length} totalCount={data.bankTransactions.length} />
                <BankTransactionsList data={{ ...data, bankTransactions: filteredTransactions }} />
              </>
            ) : (
              <>
                <FinanceBudgetOverview data={data} readOnly={demo} />
                <RecurringCostsPanel data={data as AppData} />
              </>
            )}
          </div>
        </div>
      </ModuleLayout>
    </AppShell>
  );
}

function buildImportSummary(params: Record<string, string | string[] | undefined>) {
  const imported = Number(Array.isArray(params.imported) ? params.imported[0] : params.imported);
  const skipped = Number(Array.isArray(params.skipped) ? params.skipped[0] : params.skipped);
  if (!Number.isFinite(imported) || imported <= 0) return null;
  return `${imported} ABN AMRO transacties geimporteerd${Number.isFinite(skipped) && skipped > 0 ? `, ${skipped} regels overgeslagen` : ""}.`;
}

function buildTransactionFilters(params: Record<string, string | string[] | undefined>): TransactionFilters {
  return {
    q: stringParam(params.tx_q),
    provider: stringParam(params.tx_provider),
    account: stringParam(params.tx_account),
  };
}

function buildFinanceTab(params: Record<string, string | string[] | undefined>): FinanceTab {
  return stringParam(params.tab) === "planning" ? "planning" : "overzicht";
}

function stringParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function filterBankTransactions(data: AppData, filters: TransactionFilters) {
  const q = filters.q.trim().toLowerCase();
  const accountsById = new Map(data.bankAccounts.map((account) => [account.id, account]));
  return data.bankTransactions.filter((transaction) => {
    const account = transaction.account_id ? accountsById.get(transaction.account_id) : null;
    if (filters.provider && transaction.connection_id !== filters.provider) return false;
    if (filters.account && transaction.account_id !== filters.account) return false;
    if (!q) return true;
    return [transaction.description, transaction.counterparty, transaction.category, account?.name, account?.iban, account?.provider_account_id]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(q);
  });
}

function TransactionFilterPanel({ data, filters, resultCount, totalCount }: { data: AppData; filters: TransactionFilters; resultCount: number; totalCount: number }) {
  const active = Boolean(filters.q || filters.provider || filters.account);
  return (
    <form className="card transaction-filter-panel" action="/geld" method="get" data-instant-search>
      <div className="section-head compact-section-head">
        <div>
          <h2>Transacties zoeken</h2>
          <p className="muted">
            {active ? `${resultCount} van ${totalCount} transacties` : `${totalCount} transacties beschikbaar`}
          </p>
        </div>
        {active && <Link className="button" href="/geld">Reset</Link>}
      </div>
      <div className="transaction-filter-grid">
        <div className="field">
          <label htmlFor="tx-q">Zoeken</label>
          <input id="tx-q" name="tx_q" defaultValue={filters.q} placeholder="Omschrijving, tegenpartij, categorie..." />
        </div>
        <div className="field">
          <label htmlFor="tx-provider">Bron / bank</label>
          <select id="tx-provider" name="tx_provider" defaultValue={filters.provider}>
            <option value="">Alle bronnen</option>
            {data.bankConnections.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {bankProviderLabel(connection.provider)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="tx-account">Rekening</label>
          <select id="tx-account" name="tx_account" defaultValue={filters.account}>
            <option value="">Alle rekeningen</option>
            {data.bankAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name} · {account.iban ?? account.provider_account_id}
              </option>
            ))}
          </select>
        </div>
        <button className="button primary">Filteren</button>
      </div>
    </form>
  );
}

function FinanceTabs({ activeTab }: { activeTab: FinanceTab }) {
  const tabs: Array<{ id: FinanceTab; label: string; detail: string; href: string }> = [
    { id: "overzicht", label: "Overzicht", detail: "Bank, betaalmomenten en transacties", href: "/geld" },
    { id: "planning", label: "Budget & terugkerend", detail: "Budgetten en vaste patronen", href: "/geld?tab=planning" },
  ];
  return (
    <nav className="shopping-tabs finance-tabs" aria-label="Geld onderdelen">
      {tabs.map((tab) => (
        <Link className={activeTab === tab.id ? "active" : ""} href={tab.href} key={tab.id}>
          <span>{tab.label}</span>
          <small>{tab.detail}</small>
        </Link>
      ))}
    </nav>
  );
}

function bankProviderLabel(provider: string) {
  if (provider === "abn_amro_manual") return "ABN AMRO";
  if (provider === "bunq") return "bunq";
  return provider;
}

function FinanceControlPanel({ data }: { data: AppData }) {
  const insight = buildFinanceDashboardInsight(data, new Date().toISOString());
  const nextAction = insight.nextPayment
    ? { title: insight.nextPayment.title, detail: `${money(insight.nextPayment.amount_cents)} · ${shortDate(insight.nextPayment.due_date)}`, href: "/geld" }
    : { title: insight.signalTitle, detail: insight.signalDetail, href: data.bankConnections.length === 0 ? "/geld" : "/data" };

  return (
    <section className="finance-control card">
      <div className="section-head">
        <div>
          <span className="eyebrow">Regie</span>
          <h2>Financieregie</h2>
          <p className="muted">Betaalmomenten, vaste lasten en budgetrisico in een overzicht.</p>
        </div>
        <span className={insight.signal === "urgent" || insight.signal === "attention" ? "status accent" : "status"}>
          {insight.overdueCount + insight.budgetWarningCount} aandacht
        </span>
      </div>
      <div className="finance-control-grid">
        <FinanceMetric icon={<ReceiptText size={17} />} label="Maandlasten" value={money(insight.monthlyCommittedCents)} detail="Actieve maandwaarde" />
        <FinanceMetric icon={<CalendarClock size={17} />} label="Deze week" value={money(insight.dueWeekCents)} detail={`${insight.dueWeekCount} betaalmoment${insight.dueWeekCount === 1 ? "" : "en"}`} />
        <FinanceMetric icon={<AlertTriangle size={17} />} label="Budgetalarm" value={insight.budgetWarningCount} detail="Categorieen op of boven drempel" />
        <FinanceMetric icon={<PiggyBank size={17} />} label="Zonder budget" value={money(insight.unbudgetedCents)} detail={`${insight.unbudgetedCount} categorie${insight.unbudgetedCount === 1 ? "" : "en"}`} />
      </div>
      <div className="finance-cashflow">
        <div className={`finance-signal ${insight.signal}`}>
          <span><WalletCards size={18} /></span>
          <div>
            <strong>{insight.signalTitle}</strong>
            <p>{insight.signalDetail}</p>
          </div>
        </div>
        <div className="finance-cashflow-grid">
          <FinanceMetric icon={<Banknote size={17} />} label="Bekend saldo" value={insight.bankBalanceCents === null ? "Onbekend" : money(insight.bankBalanceCents)} detail={`${data.bankAccounts.length} rekening${data.bankAccounts.length === 1 ? "" : "en"}`} />
          <FinanceMetric icon={<WalletCards size={17} />} label="Buffer na 30 dagen" value={insight.projectedBalanceCents === null ? "Onbekend" : money(insight.projectedBalanceCents)} detail={`${money(insight.dueMonthCents)} gepland`} />
          <FinanceMetric icon={<TrendingUp size={17} />} label="Inkomsten 30 dagen" value={money(insight.recentIncomeCents)} detail={`${data.bankTransactions.length} transacties bekend`} />
          <FinanceMetric icon={<TrendingDown size={17} />} label="Uitgaven 30 dagen" value={money(insight.recentExpenseCents)} detail={`Netto ${money(insight.recentNetCents)}`} />
        </div>
        <div className="finance-score-row">
          <div>
            <strong>Financiele druk</strong>
            <p className="muted">Score op basis van achterstand, budgetten, onbekende categorieen, buffer en bankkoppeling.</p>
          </div>
          <div className="finance-score">
            <span>{insight.cashflowScore}%</span>
            <div className="progress-bar" aria-hidden="true"><span style={{ width: `${insight.cashflowScore}%` }} /></div>
          </div>
        </div>
      </div>
      <div className="finance-next-row">
        <div>
          <strong>{nextAction.title}</strong>
          <p className="muted">{nextAction.detail}</p>
        </div>
        <div className="finance-action-stack">
          <span className="status">{insight.dueMonthCount} komende maand</span>
          <Link className="button" href={nextAction.href}>Open actie</Link>
        </div>
      </div>
      <div className="finance-category-tags">
        {Object.entries(insight.monthlyByCategory).slice(0, 6).map(([category, amount]) => (
          <span className="status" key={category}>{category}: {money(amount)}</span>
        ))}
        {Object.keys(insight.monthlyByCategory).length === 0 && <span className="muted">Nog geen actieve maandlasten.</span>}
      </div>
    </section>
  );
}

function FinanceMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string | number; detail: string }) {
  return (
    <div className="finance-metric">
      <span className="finance-metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function DemoPanel() {
  return (
    <div className="card">
      <h2>Demo-modus</h2>
      <p className="muted">Configureer PostgreSQL om vaste lasten, budgetten en betaalmomenten op te slaan.</p>
    </div>
  );
}
