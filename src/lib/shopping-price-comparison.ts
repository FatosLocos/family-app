import type { PriceObservation, ShoppingItem } from "@/lib/types";

export type PriceStoreId = "lidl" | "albert-heijn" | "jumbo" | "kaufland-de";

export const PRICE_CHECK_STORES: Array<{ id: PriceStoreId; label: string; country: string; aliases: string[] }> = [
  { id: "lidl", label: "Lidl", country: "NL/DE", aliases: ["lidl", "lidl nederland", "lidl nl", "lidl duitsland", "lidl de"] },
  { id: "albert-heijn", label: "Albert Heijn", country: "NL", aliases: ["albert heijn", "ah", "ah.nl", "albert-heijn"] },
  { id: "jumbo", label: "Jumbo", country: "NL", aliases: ["jumbo", "jumbo.com"] },
  { id: "kaufland-de", label: "Kaufland DE", country: "DE", aliases: ["kaufland", "kaufland de", "kaufland duitsland", "kaufland.de"] },
];

export type BasketStorePrice = {
  storeId: PriceStoreId;
  storeLabel: string;
  price: PriceObservation | null;
  isOffer: boolean;
};

export type BasketPriceRow = {
  item: ShoppingItem;
  prices: BasketStorePrice[];
  cheapest: BasketStorePrice | null;
};

export type BasketStoreTotal = {
  storeId: PriceStoreId;
  storeLabel: string;
  country: string;
  totalCents: number;
  pricedItems: number;
  missingItems: number;
  offers: number;
};

export type BasketOffer = {
  itemName: string;
  storeLabel: string;
  price: PriceObservation;
};

export type BasketPriceComparison = {
  rows: BasketPriceRow[];
  stores: BasketStoreTotal[];
  offers: BasketOffer[];
  bestStore: BasketStoreTotal | null;
  lastUpdatedAt: string | null;
  openItemCount: number;
};

export function buildBasketPriceComparison(items: ShoppingItem[], observations: PriceObservation[]): BasketPriceComparison {
  const openItems = items.filter((item) => !item.checked);
  const latestByProductStore = buildLatestPriceMap(observations);
  const rows = openItems.map((item) => {
    const productKey = normalizeProductName(item.name);
    const prices = PRICE_CHECK_STORES.map((store) => {
      const price = latestByProductStore.get(priceKey(productKey, store.id)) ?? null;
      return {
        storeId: store.id,
        storeLabel: store.label,
        price,
        isOffer: isOfferPrice(price),
      };
    });
    const cheapest = prices
      .filter((storePrice): storePrice is BasketStorePrice & { price: PriceObservation } => Boolean(storePrice.price))
      .sort((a, b) => a.price.total_price_cents - b.price.total_price_cents)[0] ?? null;
    return { item, prices, cheapest };
  });

  const stores = PRICE_CHECK_STORES.map((store) => {
    const prices = rows.map((row) => row.prices.find((price) => price.storeId === store.id)).filter(Boolean) as BasketStorePrice[];
    const pricedItems = prices.filter((price) => price.price).length;
    return {
      storeId: store.id,
      storeLabel: store.label,
      country: store.country,
      totalCents: prices.reduce((sum, price) => sum + (price.price?.total_price_cents ?? 0), 0),
      pricedItems,
      missingItems: openItems.length - pricedItems,
      offers: prices.filter((price) => price.isOffer).length,
    };
  });

  const offers = rows.flatMap((row) =>
    observations
      .filter((price) => normalizeProductName(price.product_name) === normalizeProductName(row.item.name))
      .filter((price) => isOfferPrice(price))
      .map((price) => ({ itemName: row.item.name, storeLabel: price.store ?? "Onbekende winkel", price })),
  );
  const bestStore = stores
    .filter((store) => store.pricedItems > 0)
    .sort((a, b) => a.missingItems - b.missingItems || a.totalCents - b.totalCents)[0] ?? null;
  const lastUpdatedAt = observations.reduce<string | null>((latest, price) => (!latest || price.observed_at > latest ? price.observed_at : latest), null);

  return { rows, stores, offers, bestStore, lastUpdatedAt, openItemCount: openItems.length };
}

export function normalizeProductName(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function resolvePriceStore(storeName: string | null | undefined): PriceStoreId | null {
  const normalized = normalizeProductName(storeName ?? "");
  if (!normalized) return null;
  return PRICE_CHECK_STORES.find((store) => store.aliases.some((alias) => normalized === normalizeProductName(alias) || normalized.includes(normalizeProductName(alias))))?.id ?? null;
}

export function isOfferPrice(price: PriceObservation | null) {
  if (!price) return false;
  if (price.offer_label?.trim()) return true;
  return Boolean(price.regular_price_cents && price.regular_price_cents > price.total_price_cents);
}

function buildLatestPriceMap(observations: PriceObservation[]) {
  const latest = new Map<string, PriceObservation>();
  for (const observation of observations) {
    const storeId = resolvePriceStore(observation.store);
    if (!storeId) continue;
    const key = priceKey(normalizeProductName(observation.product_name), storeId);
    const current = latest.get(key);
    if (!current || shouldReplacePrice(current, observation)) latest.set(key, observation);
  }
  return latest;
}

function shouldReplacePrice(current: PriceObservation, next: PriceObservation) {
  if (current.reliability === "aanbieding" && next.reliability !== "aanbieding") return true;
  if (current.reliability !== "aanbieding" && next.reliability === "aanbieding") return false;
  return next.observed_at > current.observed_at;
}

function priceKey(productName: string, storeId: PriceStoreId) {
  return `${productName}:${storeId}`;
}
