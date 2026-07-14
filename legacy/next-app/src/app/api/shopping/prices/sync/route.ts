import { NextResponse, type NextRequest } from "next/server";
import { fetchFreeShoppingPrices, getFreePriceProviderMetadata, type FreePriceResult } from "@/lib/checkjebon-price-provider";
import { fetchKauflandPrices, hasKauflandProvider, type KauflandPriceResult } from "@/lib/kaufland-provider";
import { fetchPrijsProfeetOffers, type OfferPriceResult } from "@/lib/prijsprofeet-provider";
import { getShoppingPriceProviderStatus, hasLocalDatabaseEnv } from "@/lib/env";
import { query } from "@/lib/local-db";
import { buildBasketPriceComparison } from "@/lib/shopping-price-comparison";
import type { PriceObservation, ShoppingItem } from "@/lib/types";

type HouseholdRow = { id: string };

type SyncResult = {
  households: number;
  inserted: number;
  skippedToday: number;
  missingPrices: number;
};

type PriceSnapshot = {
  household_id: string;
  product_id: string | null;
  product_name: string;
  store: string | null;
  unit_price_cents: number | null;
  total_price_cents: number;
  quantity: string | null;
  source: "price_check";
  regular_price_cents: number | null;
  offer_label: string | null;
  offer_valid_until: string | null;
  external_url: string | null;
  price_provider: "checkjebon" | "prijsprofeet" | "apify" | "webscraping_amsterdam" | "manual" | null;
  reliability: "indicatief" | "aanbieding" | "live_gecontroleerd" | "managed_feed" | "handmatig" | null;
  matched_product_name: string | null;
};

export async function GET() {
  const provider = getShoppingPriceProviderStatus();
  const providerMetadata = provider.id === "checkjebon" ? await getFreePriceProviderMetadata() : null;
  const kauflandConfigured = hasKauflandProvider();
  return NextResponse.json({
    ok: true,
    stores: ["Lidl", "Albert Heijn", "Jumbo", "Kaufland DE"],
    mode: provider.configured ? "live-provider-ready" : "local-price-history",
    liveProvider: provider,
    kauflandProvider: {
      configured: kauflandConfigured,
      label: kauflandConfigured ? "Apify Kaufland" : "APIFY_TOKEN ontbreekt",
    },
    providerMetadata,
    dailyEndpoint: "/api/shopping/prices/sync",
    note: provider.id === "checkjebon"
      ? `Gratis Checkjebon-provider actief voor basisprijzen en PrijsProfeet voor aanbiedingen.${kauflandConfigured ? " Kaufland DE is als experimentele Apify-bron gekoppeld, maar kan door Kaufland-botdetectie lege resultaten geven." : " Kaufland DE staat klaar, maar vereist APIFY_TOKEN."}`
      : provider.configured
      ? "Providerconfiguratie gevonden. De sync-route kan achter deze providerlaag actuele prijzen opslaan."
      : "Geen live prijsprovider geconfigureerd. Zonder externe provider worden alleen bekende prijzen ververst; ontbrekende actuele prijzen blijven gemarkeerd.",
  });
}

export async function POST(request: NextRequest) {
  const tokenError = validateSyncToken(request);
  if (tokenError) return tokenError;

  if (hasLocalDatabaseEnv()) {
    return NextResponse.json({ ok: true, ...(await syncLocalPriceHistory()) });
  }

  return NextResponse.json({ ok: false, error: "PostgreSQL is niet geconfigureerd voor prijs-sync." }, { status: 503 });
}

function validateSyncToken(request: NextRequest) {
  const expected = process.env.SHOPPING_PRICE_SYNC_TOKEN;
  if (!expected) return null;
  const actual = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "").trim();
  if (actual === expected) return null;
  return NextResponse.json({ ok: false, error: "Ongeldige prijs-sync token." }, { status: 401 });
}

async function syncLocalPriceHistory(): Promise<SyncResult> {
  const households = await query<HouseholdRow>("select id from households order by id");
  const result: SyncResult = { households: households.rows.length, inserted: 0, skippedToday: 0, missingPrices: 0 };

  for (const household of households.rows) {
    const [items, prices] = await Promise.all([
      query<ShoppingItem>("select * from shopping_items where household_id = $1 and checked = false order by created_at desc", [household.id]),
      query<PriceObservation>("select * from price_observations where household_id = $1 order by observed_at desc limit 500", [household.id]),
    ]);
    const snapshots = buildSnapshots(household.id, items.rows, prices.rows);
    const freeSnapshots = getShoppingPriceProviderStatus().id === "checkjebon"
      ? buildProviderSnapshots(
        household.id,
        await fetchFreeShoppingPrices(items.rows),
        await fetchPrijsProfeetOffers(items.rows),
        await fetchKauflandPrices(items.rows),
        prices.rows,
      )
      : null;
    result.missingPrices += freeSnapshots?.missingPrices ?? snapshots.missingPrices;
    result.skippedToday += freeSnapshots?.skippedToday ?? snapshots.skippedToday;
    for (const snapshot of freeSnapshots?.rows ?? snapshots.rows) {
      await query(
        `insert into price_observations
          (household_id, product_id, product_name, store, unit_price_cents, total_price_cents, quantity, source, regular_price_cents, offer_label, offer_valid_until, external_url, price_provider, reliability, matched_product_name)
         values ($1, $2, $3, $4, $5, $6, $7, 'price_check', $8, $9, $10, $11, $12, $13, $14)`,
        [
          snapshot.household_id,
          snapshot.product_id,
          snapshot.product_name,
          snapshot.store,
          snapshot.unit_price_cents,
          snapshot.total_price_cents,
          snapshot.quantity,
          snapshot.regular_price_cents,
          snapshot.offer_label,
          snapshot.offer_valid_until,
          snapshot.external_url,
          snapshot.price_provider,
          snapshot.reliability,
          snapshot.matched_product_name,
        ],
      );
      result.inserted += 1;
    }
  }

  return result;
}

function buildSnapshots(householdId: string, items: ShoppingItem[], prices: PriceObservation[]) {
  const comparison = buildBasketPriceComparison(items, prices);
  const today = new Date().toISOString().slice(0, 10);
  const rows: PriceSnapshot[] = [];
  let skippedToday = 0;
  let missingPrices = 0;

  for (const row of comparison.rows) {
    for (const storePrice of row.prices) {
      if (!storePrice.price) {
        missingPrices += 1;
        continue;
      }
      if (dateKey(storePrice.price.observed_at) === today) {
        skippedToday += 1;
        continue;
      }
      rows.push({
        household_id: householdId,
        product_id: row.item.product_id ?? storePrice.price.product_id ?? null,
        product_name: row.item.name,
        store: storePrice.storeLabel,
        unit_price_cents: storePrice.price.unit_price_cents,
        total_price_cents: storePrice.price.total_price_cents,
        quantity: row.item.quantity ?? storePrice.price.quantity,
        source: "price_check" as const,
        regular_price_cents: storePrice.price.regular_price_cents ?? null,
        offer_label: storePrice.price.offer_label ?? null,
        offer_valid_until: storePrice.price.offer_valid_until ?? null,
        external_url: storePrice.price.external_url ?? null,
        price_provider: storePrice.price.price_provider ?? null,
        reliability: storePrice.price.reliability ?? null,
        matched_product_name: storePrice.price.matched_product_name ?? null,
      });
    }
  }

  return { rows, skippedToday, missingPrices };
}

function buildProviderSnapshots(householdId: string, prices: FreePriceResult[], offers: OfferPriceResult[], kauflandPrices: KauflandPriceResult[], existingPrices: PriceObservation[]) {
  const today = new Date().toISOString().slice(0, 10);
  const existingToday = new Set(
    existingPrices
      .filter((price) => dateKey(price.observed_at) === today)
      .map((price) => `${price.product_name.toLowerCase()}:${price.store?.toLowerCase()}:${price.price_provider ?? "unknown"}`),
  );
  let skippedToday = 0;
  const rows: PriceSnapshot[] = [];

  for (const price of prices) {
    const key = `${price.queryName.toLowerCase()}:${price.store.toLowerCase()}:checkjebon`;
    if (existingToday.has(key)) {
      skippedToday += 1;
      continue;
    }
    rows.push({
      household_id: householdId,
      product_id: price.productId,
      product_name: price.queryName,
      store: price.store,
      unit_price_cents: price.totalPriceCents,
      total_price_cents: price.totalPriceCents,
      quantity: price.quantity,
      source: "price_check" as const,
      regular_price_cents: null,
      offer_label: null,
      offer_valid_until: null,
      external_url: price.externalUrl,
      price_provider: "checkjebon" as const,
      reliability: "indicatief" as const,
      matched_product_name: price.productName,
    });
  }

  for (const offer of offers) {
    const key = `${offer.queryName.toLowerCase()}:${offer.store.toLowerCase()}:prijsprofeet`;
    if (existingToday.has(key)) {
      skippedToday += 1;
      continue;
    }
    rows.push({
      household_id: householdId,
      product_id: offer.productId,
      product_name: offer.queryName,
      store: offer.store,
      unit_price_cents: offer.totalPriceCents,
      total_price_cents: offer.totalPriceCents,
      quantity: null,
      source: "price_check" as const,
      regular_price_cents: offer.regularPriceCents,
      offer_label: offer.offerLabel,
      offer_valid_until: offer.offerValidUntil,
      external_url: offer.externalUrl,
      price_provider: "prijsprofeet" as const,
      reliability: "aanbieding" as const,
      matched_product_name: offer.matchedProductName,
    });
  }

  for (const price of kauflandPrices) {
    const key = `${price.queryName.toLowerCase()}:kaufland de:apify`;
    if (existingToday.has(key)) {
      skippedToday += 1;
      continue;
    }
    rows.push({
      household_id: householdId,
      product_id: price.productId,
      product_name: price.queryName,
      store: "Kaufland DE",
      unit_price_cents: price.totalPriceCents,
      total_price_cents: price.totalPriceCents,
      quantity: price.quantity,
      source: "price_check" as const,
      regular_price_cents: null,
      offer_label: null,
      offer_valid_until: null,
      external_url: price.externalUrl,
      price_provider: "apify" as const,
      reliability: "live_gecontroleerd" as const,
      matched_product_name: price.matchedProductName,
    });
  }

  return { rows, skippedToday, missingPrices: 0 };
}

function dateKey(value: string | Date) {
  return (value instanceof Date ? value.toISOString() : String(value)).slice(0, 10);
}
