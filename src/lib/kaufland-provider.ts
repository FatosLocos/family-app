import type { ShoppingItem } from "@/lib/types";

type KauflandActorItem = Record<string, unknown>;

export type KauflandPriceResult = {
  productId: string | null;
  queryName: string;
  matchedProductName: string;
  totalPriceCents: number;
  quantity: string | null;
  externalUrl: string | null;
};

const defaultActorId = "e-commerce~kaufland-fast-product-scraper";
const defaultTimeoutMs = 5_000;
const defaultMaxItemsPerSync = 1;

export function hasKauflandProvider() {
  return Boolean(process.env.APIFY_TOKEN);
}

export async function fetchKauflandPrices(items: ShoppingItem[]): Promise<KauflandPriceResult[]> {
  if (!hasKauflandProvider()) return [];
  const token = process.env.APIFY_TOKEN;
  const actorId = process.env.APIFY_KAUFLAND_ACTOR_ID?.trim() || defaultActorId;
  const timeoutMs = Number(process.env.APIFY_KAUFLAND_TIMEOUT_MS ?? defaultTimeoutMs);
  const maxItemsPerSync = Number(process.env.APIFY_KAUFLAND_MAX_ITEMS_PER_SYNC ?? defaultMaxItemsPerSync);
  const results: KauflandPriceResult[] = [];

  for (const item of items.filter((entry) => !entry.checked).slice(0, Number.isFinite(maxItemsPerSync) ? maxItemsPerSync : defaultMaxItemsPerSync)) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), Number.isFinite(timeoutMs) ? timeoutMs : defaultTimeoutMs);
      const response = await fetch(`https://api.apify.com/v2/acts/${actorId}/run-sync-get-dataset-items?token=${encodeURIComponent(token!)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify(buildActorInput(actorId, item.name)),
      });
      clearTimeout(timeout);
      if (!response.ok) {
        console.warn(`Kaufland prijscheck overgeslagen (${response.status}).`);
        continue;
      }
      const actorItems = (await response.json()) as KauflandActorItem[];
      const match = bestKauflandMatch(actorItems, item.name);
      if (!match) continue;
      results.push({
        productId: item.product_id ?? null,
        queryName: item.name,
        matchedProductName: match.name,
        totalPriceCents: match.totalPriceCents,
        quantity: match.quantity,
        externalUrl: match.externalUrl,
      });
    } catch (error) {
      const message = error instanceof Error && error.name === "AbortError" ? "timeout" : "onbekende fout";
      console.warn(`Kaufland prijscheck overgeslagen (${message}).`);
    }
  }

  return results;
}

function buildActorInput(actorId: string, keyword: string) {
  if (actorId.includes("piotrv1001") || actorId.includes("kaufland-listings-scraper")) {
    return {
      searchQueries: [keyword],
      country: "de",
      maxItems: 1,
      scrapeProductDetails: false,
      startUrls: [],
    };
  }
  return {
    keyword,
    maxProductsPerCategory: 1,
    startUrlsCategories: [],
  };
}

export function bestKauflandMatch(items: KauflandActorItem[], query: string) {
  return items
    .map((item) => normalizeActorItem(item, query))
    .filter((item): item is NonNullable<ReturnType<typeof normalizeActorItem>> => Boolean(item))
    .filter((item) => isReasonableMatch(item.name, query))
    .sort((a, b) => a.score - b.score || a.totalPriceCents - b.totalPriceCents)[0] ?? null;
}

function normalizeActorItem(item: KauflandActorItem, query: string) {
  const name = stringValue(item.title) ?? stringValue(item.name) ?? stringValue(item.productName);
  const priceValue = item.price ?? item.currentPrice ?? item.salePrice ?? item.finalPrice;
  const totalPriceCents = priceToCents(priceValue);
  if (!name || totalPriceCents === null) return null;
  return {
    name,
    totalPriceCents,
    quantity: stringValue(item.quantity) ?? stringValue(item.unit) ?? stringValue(item.packageSize),
    externalUrl: stringValue(item.url) ?? stringValue(item.productUrl) ?? stringValue(item.link),
    score: matchScore(name, stringValue(item.brand), query),
  };
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function priceToCents(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.round(value * 100);
  if (typeof value === "string") {
    const normalized = value.replace(/[^\d,.]/g, "").replace(",", ".");
    const parsed = Number.parseFloat(normalized);
    return Number.isFinite(parsed) ? Math.round(parsed * 100) : null;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return priceToCents(record.value ?? record.amount ?? record.price);
  }
  return null;
}

function isReasonableMatch(name: string, query: string) {
  const nameTokens = productTokens(name);
  const queryTokens = productTokens(query);
  if (queryTokens.length === 0) return false;
  if (nameTokens.some((token) => ["duschgel", "shampoo", "deo", "kosmetik", "salat", "salade"].includes(token))) return false;
  return queryTokens.every((token) => {
    const aliases = tokenAliases(token);
    return aliases.some((alias) => nameTokens.some((word) => word === alias || word === `${alias}s` || word === `${alias}n` || word.endsWith(alias)));
  });
}

function matchScore(name: string, brand: string | null, query: string) {
  const normalizedName = normalize(`${brand ?? ""} ${name}`);
  const normalizedQuery = normalize(query);
  let score = normalizedName.includes(normalizedQuery) ? 0 : 30;
  score += Math.abs(normalizedName.length - normalizedQuery.length) / 12;
  return score;
}

function productTokens(value: string) {
  return normalize(value)
    .split(" ")
    .filter((token) => token.length > 2)
    .filter((token) => !["kaufland", "kclassic", "k", "bio", "deutschland"].includes(token));
}

function tokenAliases(token: string) {
  const aliases: Record<string, string[]> = {
    komkommer: ["komkommer", "gurke"],
    cucumber: ["cucumber", "gurke", "komkommer"],
    gurke: ["gurke", "komkommer"],
  };
  return aliases[token] ?? [token];
}

function normalize(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
