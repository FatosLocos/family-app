import type { ShoppingItem } from "@/lib/types";

type CheckjebonProduct = {
  n: string;
  l?: string;
  p: number;
  s?: string;
};

type CheckjebonStore = {
  n: string;
  c: string;
  u?: string;
  d?: CheckjebonProduct[];
};

export type FreePriceResult = {
  productName: string;
  productId: string | null;
  queryName: string;
  store: "Albert Heijn" | "Jumbo" | "Lidl";
  totalPriceCents: number;
  quantity: string | null;
  externalUrl: string | null;
  priceProvider: "checkjebon";
  reliability: "indicatief";
};

type ProductCandidate = {
  product: CheckjebonProduct;
  score: number;
  quantityGrams: number | null;
};

const checkjebonUrl = "https://www.checkjebon.nl/data/supermarkets.json";
const cacheTtlMs = 60 * 60 * 1000;
const storeMap = new Map([
  ["ah", "Albert Heijn" as const],
  ["jumbo", "Jumbo" as const],
  ["lidl", "Lidl" as const],
]);

let cache: { fetchedAt: number; data: CheckjebonStore[]; lastModified: string | null } | null = null;

export async function fetchFreeShoppingPrices(items: ShoppingItem[]): Promise<FreePriceResult[]> {
  const stores = await getCheckjebonData();
  const openItems = items.filter((item) => !item.checked);
  const results: FreePriceResult[] = [];

  for (const item of openItems) {
    const candidatesByStore = stores
      .map((store) => {
        const storeName = storeMap.get(store.n);
        if (!storeName || !store.d?.length) return null;
        const candidates = findProducts(store.d, item);
        return candidates.length > 0 ? { store, storeName, candidates } : null;
      })
      .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));
    const targetQuantityGrams = resolveTargetQuantityGrams(item, candidatesByStore.flatMap((entry) => entry.candidates));

    for (const entry of candidatesByStore) {
      const match = chooseStoreProduct(entry.candidates, targetQuantityGrams);
      if (!match) continue;
      results.push({
        productName: match.product.n,
        productId: item.product_id ?? null,
        queryName: item.name,
        store: entry.storeName,
        totalPriceCents: Math.round(match.product.p * 100),
        quantity: match.product.s || item.quantity || quantityFromName(match.product.n) || null,
        externalUrl: match.product.l && entry.store.u ? entry.store.u + match.product.l : null,
        priceProvider: "checkjebon",
        reliability: "indicatief",
      });
    }
  }

  return results;
}

async function getCheckjebonData() {
  if (cache && Date.now() - cache.fetchedAt < cacheTtlMs) return cache.data;
  const response = await fetch(checkjebonUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`Checkjebon prijsdata niet beschikbaar (${response.status}).`);
  const data = (await response.json()) as CheckjebonStore[];
  cache = { fetchedAt: Date.now(), data, lastModified: response.headers.get("last-modified") };
  return data;
}

export async function getFreePriceProviderMetadata() {
  await getCheckjebonData();
  return {
    provider: "Checkjebon",
    sourceUrl: checkjebonUrl,
    cachedAt: cache ? new Date(cache.fetchedAt).toISOString() : null,
    lastModified: cache?.lastModified ?? null,
  };
}

function findProducts(products: CheckjebonProduct[], item: ShoppingItem): ProductCandidate[] {
  const queryTokens = searchableTokens(`${item.quantity ?? ""} ${item.name}`);
  const requiredTokens = requiredSearchTokens(queryTokens);
  if (requiredTokens.length === 0) return [];
  return products
    .filter((product) => isProductCandidate(product, requiredTokens, queryTokens))
    .map((product) => ({
      product,
      score: scoreProduct(product, queryTokens, item.name),
      quantityGrams: parsePackageGrams(`${product.s ?? ""} ${product.n}`),
    }))
    .sort((a, b) => a.score - b.score || a.product.p - b.product.p);
}

function chooseStoreProduct(candidates: ProductCandidate[], targetQuantityGrams: number | null) {
  if (!targetQuantityGrams) return candidates[0] ?? null;
  return candidates
    .slice()
    .sort((a, b) => quantityDistance(a.quantityGrams, targetQuantityGrams) - quantityDistance(b.quantityGrams, targetQuantityGrams) || a.score - b.score || a.product.p - b.product.p)[0] ?? null;
}

function resolveTargetQuantityGrams(item: ShoppingItem, candidates: ProductCandidate[]) {
  const explicitQuantity = parsePackageGrams(`${item.quantity ?? ""} ${item.name}`);
  if (explicitQuantity) return explicitQuantity;
  const grouped = new Map<number, number>();
  for (const candidate of candidates) {
    if (!candidate.quantityGrams) continue;
    grouped.set(candidate.quantityGrams, (grouped.get(candidate.quantityGrams) ?? 0) + 1);
  }
  return [...grouped.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0]?.[0] ?? null;
}

function isProductCandidate(product: CheckjebonProduct, requiredTokens: string[], queryTokens: string[]) {
  const normalized = normalize(product.n);
  if (!requiredTokens.every((token) => normalized.includes(token))) return false;
  if (queryTokens.some((token) => spreadTokens.has(token)) && excludedSpreadProductTokens.some((token) => normalized.includes(token))) return false;
  return true;
}

function requiredSearchTokens(tokens: string[]) {
  const hasSpecificToken = tokens.some((token) => !genericProductTokens.has(token));
  return hasSpecificToken ? tokens.filter((token) => !genericProductTokens.has(token)) : tokens;
}

function scoreProduct(product: CheckjebonProduct, queryTokens: string[], itemName: string) {
  const normalizedName = normalize(product.n);
  const normalizedItem = normalize(itemName);
  let score = normalizedName.length / 100;
  if (normalizedName === normalizedItem) score -= 20;
  if (normalizedName.endsWith(` ${normalizedItem}`)) score -= 10;
  if (normalizedName.includes(` ${normalizedItem} `)) score -= 5;
  for (const token of queryTokens) score += Math.max(0, normalizedName.indexOf(token)) / 1000;
  return score;
}

function searchableTokens(value: string) {
  return normalize(value)
    .split(" ")
    .filter(Boolean)
    .filter((token) => !/^\d+([.,]\d+)?$/.test(token))
    .filter((token) => !["x", "stuk", "stuks", "per", "gram", "gr", "g", "kg", "kilo", "ml", "liter", "l"].includes(token));
}

function quantityDistance(value: number | null, target: number) {
  if (!value) return Number.MAX_SAFE_INTEGER;
  return Math.abs(value - target);
}

function parsePackageGrams(value: string) {
  const normalized = value
    .toLowerCase()
    .replace(/,/g, ".")
    .replace(/\bgr\b/g, "g")
    .replace(/(\d)gr\b/g, "$1 g")
    .replace(/[^a-z0-9.]+/g, " ")
    .trim();
  const multi = normalized.match(/(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(kg|kilo|g|gram)\b/);
  if (multi) return Math.round(toNumber(multi[1]) * toGrams(toNumber(multi[2]), multi[3]));
  const single = normalized.match(/(\d+(?:\.\d+)?)\s*(kg|kilo|g|gram)\b/);
  if (single) return Math.round(toGrams(toNumber(single[1]), single[2]));
  return null;
}

function quantityFromName(value: string) {
  const grams = parsePackageGrams(value);
  return grams ? `${grams} g` : null;
}

function toNumber(value: string) {
  return Number.parseFloat(value.replace(",", "."));
}

function toGrams(value: number, unit: string) {
  return unit === "kg" || unit === "kilo" ? value * 1000 : value;
}

const genericProductTokens = new Set(["pasta", "hazelnootpasta", "chocopasta"]);
const spreadTokens = new Set(["pasta", "hazelnootpasta", "chocopasta"]);
const excludedSpreadProductTokens = ["b ready", "bready", "biscuit", "biscuits", "go", "snack", "sticks", "dip"];

function normalize(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
