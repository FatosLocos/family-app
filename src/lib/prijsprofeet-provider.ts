import type { ShoppingItem } from "@/lib/types";

type PrijsProfeetResult = {
  name: string;
  price: number | null;
  original_price: number | null;
  retailer: string;
  product_url: string | null;
  is_promotional: boolean;
  promotional_keywords: string[] | null;
  promotion_type: string | null;
  valid_until: string | null;
  score: number | null;
  unified_category: string | null;
};

type PrijsProfeetSearchResponse = {
  results?: PrijsProfeetResult[];
};

export type OfferPriceResult = {
  productId: string | null;
  queryName: string;
  matchedProductName: string;
  store: "Albert Heijn" | "Jumbo" | "Lidl";
  totalPriceCents: number;
  regularPriceCents: number | null;
  offerLabel: string | null;
  offerValidUntil: string | null;
  externalUrl: string | null;
};

const retailerMap = new Map([
  ["albert_heijn", "Albert Heijn" as const],
  ["jumbo", "Jumbo" as const],
  ["lidl", "Lidl" as const],
]);

export async function fetchPrijsProfeetOffers(items: ShoppingItem[]): Promise<OfferPriceResult[]> {
  const results: OfferPriceResult[] = [];
  for (const item of items.filter((entry) => !entry.checked)) {
    const response = await fetch(`https://www.prijsprofeet.nl/api/v1/search?q=${encodeURIComponent(item.name)}&page_size=20`, {
      cache: "no-store",
      headers: { "user-agent": "FamilyApp/1.0" },
    });
    if (!response.ok) continue;
    const json = (await response.json()) as PrijsProfeetSearchResponse;
    const bestByRetailer = bestOfferByRetailer(json.results ?? [], item.name);
    for (const offer of bestByRetailer) {
      results.push({
        productId: item.product_id ?? null,
        queryName: item.name,
        matchedProductName: offer.name,
        store: retailerMap.get(offer.retailer)!,
        totalPriceCents: Math.round((offer.price ?? 0) * 100),
        regularPriceCents: typeof offer.original_price === "number" ? Math.round(offer.original_price * 100) : null,
        offerLabel: offerLabel(offer),
        offerValidUntil: normalizeValidUntil(offer.valid_until),
        externalUrl: offer.product_url,
      });
    }
  }
  return results;
}

function bestOfferByRetailer(results: PrijsProfeetResult[], query: string) {
  const byRetailer = new Map<string, PrijsProfeetResult>();
  for (const result of results) {
    if (!retailerMap.has(result.retailer)) continue;
    if (!result.is_promotional || typeof result.price !== "number") continue;
    if (isIrrelevantCategory(result.unified_category)) continue;
    if (!hasReasonableNameMatch(result.name, query)) continue;
    const current = byRetailer.get(result.retailer);
    if (!current || scoreOffer(result, query) < scoreOffer(current, query)) byRetailer.set(result.retailer, result);
  }
  return [...byRetailer.values()];
}

function isIrrelevantCategory(category: string | null) {
  return ["drogisterij", "baby-drogisterij", "huishouden"].includes(category ?? "");
}

function hasReasonableNameMatch(name: string, query: string) {
  const queryTokens = normalize(query).split(" ").filter((token) => token.length > 2);
  const productTokens = stripBrandTokens(normalize(name).split(" ").filter((token) => token.length > 2));
  if (queryTokens.length === 0 || productTokens.length === 0) return false;
  if (queryTokens.length === 1) {
    return productTokens.length === 1 && sameProductWord(productTokens[0], queryTokens[0]);
  }
  return queryTokens.length === productTokens.length && queryTokens.every((token, index) => sameProductWord(productTokens[index], token));
}

function stripBrandTokens(tokens: string[]) {
  const brands = new Set(["ah", "jumbo", "plus", "lidl", "aldi", "dirk", "dekamarkt", "deka", "dekaVers".toLowerCase()]);
  return tokens.filter((token) => !brands.has(token));
}

function sameProductWord(productWord: string, queryWord: string) {
  if (productWord === queryWord) return true;
  if (productWord.endsWith("en") && productWord.slice(0, -2) === queryWord) return true;
  if (productWord.endsWith("s") && productWord.slice(0, -1) === queryWord) return true;
  if (queryWord.endsWith("en") && queryWord.slice(0, -2) === productWord) return true;
  if (queryWord.endsWith("s") && queryWord.slice(0, -1) === productWord) return true;
  return false;
}

function scoreOffer(result: PrijsProfeetResult, query: string) {
  const normalizedName = normalize(result.name);
  const normalizedQuery = normalize(query);
  let score = normalizedName.includes(normalizedQuery) ? 0 : 50;
  score += Math.max(0, normalizedName.length - normalizedQuery.length) / 10;
  if (typeof result.score === "number") score -= Math.min(result.score, 200) / 200;
  const discount = typeof result.original_price === "number" && typeof result.price === "number" ? result.original_price - result.price : 0;
  score -= Math.max(0, discount);
  return score;
}

function offerLabel(result: PrijsProfeetResult) {
  const keywords = result.promotional_keywords?.filter(Boolean) ?? [];
  if (keywords[0]) return keywords[0];
  if (result.promotion_type) return result.promotion_type.replace(/_/g, " ");
  return "Aanbieding";
}

function normalizeValidUntil(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return date.toISOString().slice(0, 10);
}

function normalize(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
