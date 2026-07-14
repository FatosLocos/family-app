import { describe, expect, it } from "vitest";
import { buildFinanceDashboardInsight, buildMonthlyByCategory, buildRecurringCashflowTrend, buildRecurringCostInsights, recurringTransactionRuleIdentity } from "@/lib/finance-insights";
import type { AppData } from "@/lib/types";

const baseData: Pick<AppData, "financeItems" | "financeBudgets" | "bankAccounts" | "bankTransactions" | "bankConnections"> = {
  financeItems: [],
  financeBudgets: [],
  bankAccounts: [],
  bankTransactions: [],
  bankConnections: [],
};

describe("buildMonthlyByCategory", () => {
  it("normalizes monthly and yearly active items", () => {
    const result = buildMonthlyByCategory([
      financeItem({ id: "rent", category: "Wonen", amount_cents: 120000, frequency: "maandelijks" }),
      financeItem({ id: "insurance", category: "Verzekering", amount_cents: 120000, frequency: "jaarlijks" }),
      financeItem({ id: "paid", category: "Wonen", amount_cents: 2500, frequency: "maandelijks", status: "betaald" }),
      financeItem({ id: "one-off", category: "Extra", amount_cents: 5000, frequency: "eenmalig" }),
    ]);

    expect(result).toEqual({ Wonen: 120000, Verzekering: 10000 });
  });
});

describe("buildFinanceDashboardInsight", () => {
  it("reports setup when no bank connection exists", () => {
    const insight = buildFinanceDashboardInsight(baseData, "2026-07-11T08:00:00.000Z");

    expect(insight.signal).toBe("setup");
    expect(insight.projectedBalanceCents).toBeNull();
  });

  it("flags a negative projected balance as urgent", () => {
    const insight = buildFinanceDashboardInsight({
      ...baseData,
      financeItems: [financeItem({ amount_cents: 90000, due_date: "2026-07-20" })],
      bankConnections: [{ id: "bank", household_id: "hh", provider: "bunq", environment: "sandbox", status: "configured", last_sync_at: null }],
      bankAccounts: [{ id: "acc", household_id: "hh", connection_id: "bank", provider_account_id: "1", name: "Gezamenlijk", iban: null, currency: "EUR", balance_cents: 50000 }],
    }, "2026-07-11T08:00:00.000Z");

    expect(insight.signal).toBe("urgent");
    expect(insight.projectedBalanceCents).toBe(-40000);
  });

  it("counts Date due dates from local Postgres", () => {
    const insight = buildFinanceDashboardInsight({
      ...baseData,
      financeItems: [financeItem({ due_date: new Date(2026, 6, 12) as unknown as string })],
    }, "2026-07-11T08:00:00.000Z");

    expect(insight.dueWeekCount).toBe(1);
    expect(insight.nextPayment?.id).toBe("finance");
  });

  it("counts budget warnings and recent transaction trend", () => {
    const insight = buildFinanceDashboardInsight({
      ...baseData,
      financeItems: [financeItem({ category: "Boodschappen", amount_cents: 85000 })],
      financeBudgets: [{ id: "budget", household_id: "hh", category: "Boodschappen", monthly_limit_cents: 100000, alert_threshold: 0.8 }],
      bankConnections: [{ id: "bank", household_id: "hh", provider: "bunq", environment: "sandbox", status: "configured", last_sync_at: null }],
      bankTransactions: [
        { id: "income", household_id: "hh", connection_id: "bank", account_id: null, provider_transaction_id: "i", booked_at: "2026-07-10", description: "Salaris", counterparty: null, amount_cents: 250000, currency: "EUR", category: null },
        { id: "expense", household_id: "hh", connection_id: "bank", account_id: null, provider_transaction_id: "e", booked_at: "2026-07-09", description: "Supermarkt", counterparty: null, amount_cents: -7500, currency: "EUR", category: null },
      ],
    }, "2026-07-11T08:00:00.000Z");

    expect(insight.budgetWarningCount).toBe(1);
    expect(insight.recentIncomeCents).toBe(250000);
    expect(insight.recentExpenseCents).toBe(7500);
    expect(insight.recentNetCents).toBe(242500);
  });
});

describe("buildRecurringCostInsights", () => {
  it("detects recurring monthly expenses", () => {
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "a", booked_at: "2026-04-01", description: "Netflix", amount_cents: -1599 }),
          transaction({ id: "b", booked_at: "2026-05-01", description: "Netflix", amount_cents: -1599 }),
          transaction({ id: "c", booked_at: "2026-06-01", description: "Netflix", amount_cents: -1599 }),
          transaction({ id: "d", booked_at: "2026-07-01", description: "Netflix", amount_cents: -1599 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]).toMatchObject({
      title: "Netflix",
      cadence: "maandelijks",
      confidence: "hoog",
      averageAmountCents: 1599,
      monthlyEstimateCents: 1599,
    });
  });

  it("detects recurring monthly income", () => {
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "salary-a", booked_at: "2026-04-25", description: "SALARIS WERKGEVER", amount_cents: 325000 }),
          transaction({ id: "salary-b", booked_at: "2026-05-25", description: "SALARIS WERKGEVER", amount_cents: 325000 }),
          transaction({ id: "salary-c", booked_at: "2026-06-25", description: "SALARIS WERKGEVER", amount_cents: 325000 }),
          transaction({ id: "salary-d", booked_at: "2026-07-25", description: "SALARIS WERKGEVER", amount_cents: 325000 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]).toMatchObject({
      title: "Salaris Werkgever",
      direction: "income",
      cadence: "maandelijks",
      confidence: "hoog",
      monthlyEstimateCents: 325000,
    });
  });

  it("uses the lowest recurring income unless three higher amounts repeat", () => {
    const conservative = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "income-a", booked_at: "2026-04-25", description: "SALARIS WERKGEVER", amount_cents: 300000 }),
          transaction({ id: "income-b", booked_at: "2026-05-25", description: "SALARIS WERKGEVER", amount_cents: 300000 }),
          transaction({ id: "income-c", booked_at: "2026-06-25", description: "SALARIS WERKGEVER", amount_cents: 380000 }),
          transaction({ id: "income-d", booked_at: "2026-07-25", description: "SALARIS WERKGEVER", amount_cents: 300000 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );
    const raised = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "raise-a", booked_at: "2026-04-25", description: "SALARIS WERKGEVER", amount_cents: 300000 }),
          transaction({ id: "raise-b", booked_at: "2026-05-25", description: "SALARIS WERKGEVER", amount_cents: 380000 }),
          transaction({ id: "raise-c", booked_at: "2026-06-25", description: "SALARIS WERKGEVER", amount_cents: 382000 }),
          transaction({ id: "raise-d", booked_at: "2026-07-25", description: "SALARIS WERKGEVER", amount_cents: 381000 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(conservative[0]?.monthlyEstimateCents).toBe(300000);
    expect(raised[0]?.monthlyEstimateCents).toBe(381000);
  });

  it("ignores incidental tiny income payouts when choosing the conservative salary basis", () => {
    const description = "/TRTP/SEPA Overboeking/IBAN/NL61ABNA0810637774/BIC/ABNANL2A/NAME/VAN DORP DIENSTENCENTRUM/REMI/Salaris";
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "jan-extra", booked_at: "2026-01-23", description, amount_cents: 1000 }),
          transaction({ id: "jan", booked_at: "2026-01-23", description, amount_cents: 225759 }),
          transaction({ id: "feb", booked_at: "2026-02-24", description, amount_cents: 231129 }),
          transaction({ id: "mar", booked_at: "2026-03-24", description, amount_cents: 323628 }),
          transaction({ id: "apr", booked_at: "2026-04-24", description, amount_cents: 204834 }),
          transaction({ id: "may", booked_at: "2026-05-22", description, amount_cents: 203834 }),
          transaction({ id: "jun", booked_at: "2026-06-24", description, amount_cents: 302937 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]).toMatchObject({
      title: "Van Dorp Dienstencentrum",
      direction: "income",
      monthlyEstimateCents: 203834,
    });
  });

  it("builds a monthly trend from recognized recurring income and expenses", () => {
    const trend = buildRecurringCashflowTrend(
      {
        bankTransactions: [
          transaction({ id: "salary-apr", booked_at: "2026-04-25", description: "SALARIS", amount_cents: 300000 }),
          transaction({ id: "salary-may", booked_at: "2026-05-25", description: "SALARIS", amount_cents: 300000 }),
          transaction({ id: "salary-jun", booked_at: "2026-06-25", description: "SALARIS", amount_cents: 300000 }),
          transaction({ id: "rent-apr", booked_at: "2026-04-01", description: "HUUR", amount_cents: -120000 }),
          transaction({ id: "rent-may", booked_at: "2026-05-01", description: "HUUR", amount_cents: -120000 }),
          transaction({ id: "rent-jun", booked_at: "2026-06-01", description: "HUUR", amount_cents: -120000 }),
          transaction({ id: "one-off", booked_at: "2026-06-12", description: "VAKANTIEGELD", amount_cents: 90000 }),
        ],
      },
      "2026-06-30T12:00:00.000Z",
      3,
    );

    expect(trend.map((point) => point.month)).toEqual(["2026-04", "2026-05", "2026-06"]);
    expect(trend[2]).toMatchObject({
      incomeCents: 300000,
      expenseCents: 120000,
      netCents: 180000,
    });
  });

  it("normalizes SEPA slash fields to the merchant name", () => {
    const description = "TRTP/SEPA Incasso algemeen doorlopend/CSID/DE23ZZZ00001986600/NAME/STPARKEERGELDEN VIA RIVERTY/MARF/EC004/REMI/Id";
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "a", booked_at: "2026-05-10", description, amount_cents: -1240 }),
          transaction({ id: "b", booked_at: "2026-06-10", description, amount_cents: -1180 }),
          transaction({ id: "c", booked_at: "2026-07-10", description, amount_cents: -1300 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]?.title).toBe("Stparkeergelden Via Riverty");
    expect(insights[0]?.cadence).toBe("maandelijks");
  });

  it("treats a SEPA direct debit mandate as a recurring candidate with limited history", () => {
    const description = "TRTP/SEPA Incasso algemeen doorlopend/CSID/NL00ZZZ/NAME/SPORTCLUB/MARF/MANDATE-1/REMI/Contributie";
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [transaction({ id: "a", booked_at: "2026-07-10", description, amount_cents: -2750 })],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]).toMatchObject({
      title: "Sportclub",
      cadence: "maandelijks",
      confidence: "middel",
      monthlyEstimateCents: 2750,
    });
  });

  it("groups old and slash SEPA export formats by mandate", () => {
    const oldFormat = "SEPA Incasso algemeen doorlopend Incassant: BE39ZZZCITD000000037 Naam: Butternut Box Machtiging: HHJZAT4V5GRHYNDG Omschrijving: BUTTERNUT BOX IBAN: IE30";
    const slashFormat = "/TRTP/SEPA Incasso algemeen doorlopend/CSID/BE39ZZZCITD000000037/NAME/Butternut Box/MARF/HHJZAT4V5GRHYNDG/REMI/BUTTERNUT BOX";
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "a", booked_at: "2026-03-18", description: oldFormat, amount_cents: -10624 }),
          transaction({ id: "b", booked_at: "2026-04-24", description: slashFormat, amount_cents: -10624 }),
          transaction({ id: "c", booked_at: "2026-05-27", description: slashFormat, amount_cents: -10624 }),
          transaction({ id: "d", booked_at: "2026-07-01", description: slashFormat, amount_cents: -11449 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]).toMatchObject({
      title: "Butternut Box",
      cadence: "maandelijks",
      count: 4,
    });
  });

  it("prioritizes frequently seen high confidence recurring costs", () => {
    const many = Array.from({ length: 6 }, (_, index) =>
      transaction({
        id: `asr-${index}`,
        booked_at: `2026-0${index + 1}-02`,
        description: "/TRTP/SEPA Incasso algemeen doorlopend/CSID/NL76ZZZ/NAME/ASR SCHADEVERZEKERING/MARF/070000036969/REMI/Premie",
        amount_cents: -14938,
      }),
    );
    const expensive = [
      transaction({ id: "card-a", booked_at: "2026-05-26", description: "INT CARD SERVICES", amount_cents: -450000 }),
      transaction({ id: "card-b", booked_at: "2026-06-26", description: "INT CARD SERVICES", amount_cents: -450000 }),
      transaction({ id: "card-c", booked_at: "2026-07-26", description: "INT CARD SERVICES", amount_cents: -450000 }),
    ];

    const insights = buildRecurringCostInsights({ bankTransactions: [...expensive, ...many] }, "2026-07-13T12:00:00.000Z", 5);

    expect(insights[0]?.title).toBe("Asr Schadeverzekering");
  });

  it("keeps SEPA mandates recurring despite a pro-rated outlier", () => {
    const description = "/TRTP/SEPA Incasso algemeen doorlopend/CSID/NL76ZZZ300756470003/NAME/ASR SCHADEVERZEKERING/MARF/070000036969/REMI/Premie";
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "jan", booked_at: "2026-01-02", description, amount_cents: -14225 }),
          transaction({ id: "feb", booked_at: "2026-02-02", description, amount_cents: -14225 }),
          transaction({ id: "feb-extra", booked_at: "2026-02-06", description, amount_cents: -2301 }),
          transaction({ id: "mar", booked_at: "2026-03-02", description, amount_cents: -14938 }),
          transaction({ id: "apr", booked_at: "2026-04-01", description, amount_cents: -14938 }),
          transaction({ id: "may", booked_at: "2026-05-04", description, amount_cents: -14938 }),
          transaction({ id: "jun", booked_at: "2026-06-01", description, amount_cents: -14938 }),
          transaction({ id: "jul", booked_at: "2026-07-01", description, amount_cents: -14938 }),
        ],
      },
      "2026-07-13T12:00:00.000Z",
      5,
    );

    expect(insights[0]).toMatchObject({
      title: "Asr Schadeverzekering",
      confidence: "hoog",
      averageAmountCents: 14938,
      monthlyEstimateCents: 14938,
    });
  });

  it("allows users to force or exclude recurring groups", () => {
    const description = "ADAM MARKT";
    const identity = recurringTransactionRuleIdentity(description);
    const forced = buildRecurringCostInsights(
      {
        bankTransactions: [transaction({ id: "market", booked_at: "2026-07-10", description, amount_cents: -2250 })],
        recurringTransactionRules: [
          { id: "rule", household_id: "hh", rule_key: identity.ruleKey, label: identity.label, action: "force_recurring", group_id: null, created_at: "2026-07-13", updated_at: "2026-07-13" },
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );
    const excluded = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "a", booked_at: "2026-05-10", description, amount_cents: -2250 }),
          transaction({ id: "b", booked_at: "2026-06-10", description, amount_cents: -2250 }),
          transaction({ id: "c", booked_at: "2026-07-10", description, amount_cents: -2250 }),
        ],
        recurringTransactionRules: [
          { id: "rule", household_id: "hh", rule_key: identity.ruleKey, label: identity.label, action: "exclude_recurring", group_id: null, created_at: "2026-07-13", updated_at: "2026-07-13" },
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(forced[0]?.title).toBe("Adam Markt");
    expect(forced[0]?.confidence).toBe("middel");
    expect(excluded).toHaveLength(0);
  });

  it("keeps a manual recurring cost group on the insight", () => {
    const description = "TRTP/SEPA Incasso algemeen doorlopend/NAME/ASR SCHADEVERZEKERING/MARF/ABC123/CSID/NL12ZZZ";
    const identity = recurringTransactionRuleIdentity(description);
    const insights = buildRecurringCostInsights(
      {
        bankTransactions: [
          transaction({ id: "a", booked_at: "2026-05-10", description, amount_cents: -12500 }),
          transaction({ id: "b", booked_at: "2026-06-10", description, amount_cents: -12500 }),
          transaction({ id: "c", booked_at: "2026-07-10", description, amount_cents: -12500 }),
        ],
        recurringTransactionRules: [
          { id: "rule", household_id: "hh", rule_key: identity.ruleKey, label: identity.label, action: "group_recurring", group_id: "insurance", created_at: "2026-07-13", updated_at: "2026-07-13" },
        ],
      },
      "2026-07-13T12:00:00.000Z",
    );

    expect(insights[0]?.groupId).toBe("insurance");
  });
});

function financeItem(overrides: Partial<AppData["financeItems"][number]> = {}): AppData["financeItems"][number] {
  return {
    id: "finance",
    household_id: "hh",
    title: "Vaste last",
    category: "Vaste lasten",
    amount_cents: 10000,
    frequency: "maandelijks",
    due_date: "2026-07-15",
    status: "actief",
    ...overrides,
  };
}

function transaction(overrides: Partial<AppData["bankTransactions"][number]>): AppData["bankTransactions"][number] {
  return {
    id: "tx",
    household_id: "hh",
    connection_id: "bank",
    account_id: null,
    provider_transaction_id: "provider-tx",
    booked_at: "2026-07-01",
    description: "Transactie",
    counterparty: null,
    amount_cents: -1000,
    currency: "EUR",
    category: "Abonnementen",
    ...overrides,
  };
}
