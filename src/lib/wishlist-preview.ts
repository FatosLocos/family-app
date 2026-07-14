export type WishlistPreview = {
  title: string | null;
  image_url: string | null;
  category: string | null;
  price_cents: number | null;
  price: string | null;
};

export function parseWishlistPreview(html: string, pageUrl: string): WishlistPreview {
  const jsonLd = parseJsonLdObjects(html);
  const priceCents = firstNumber([
    metaContent(html, "property", "product:price:amount"),
    metaContent(html, "property", "product:price"),
    metaContent(html, "property", "og:price:amount"),
    metaContent(html, "property", "og:price"),
    metaContent(html, "name", "price"),
    metaContent(html, "name", "twitter:data1"),
    itemPropContent(html, "price"),
    itemPropContent(html, "lowPrice"),
    itemPropContent(html, "highPrice"),
    ...jsonLd.flatMap((item) => offerPrices(item)),
  ]);

  const title =
    metaContent(html, "property", "og:title") ??
    metaContent(html, "name", "twitter:title") ??
    firstString(jsonLd.map((item) => stringValue(item["name"]))) ??
    tagText(html, "title");
  const category =
    metaContent(html, "property", "product:category") ??
    metaContent(html, "name", "category") ??
    firstString(jsonLd.map((item) => stringValue(item["category"]))) ??
    firstString(jsonLd.map((item) => breadcrumbCategory(item)));
  const image =
    metaContent(html, "property", "og:image") ??
    metaContent(html, "name", "twitter:image") ??
    firstString(jsonLd.map((item) => imageValue(item["image"])));

  return {
    title: cleanText(title),
    image_url: image ? absolutizeUrl(image, pageUrl) : null,
    category: cleanText(category),
    price_cents: priceCents,
    price: priceCents === null ? null : formatEuroInput(priceCents),
  };
}

function metaContent(html: string, attr: "name" | "property", value: string) {
  const tags = html.matchAll(/<meta\s+[^>]*>/gi);
  for (const tag of tags) {
    if (attributeValue(tag[0], attr)?.toLowerCase() === value.toLowerCase()) return attributeValue(tag[0], "content");
  }
  return null;
}

function itemPropContent(html: string, value: string) {
  const tags = html.matchAll(/<(?:meta|span|div|p)\s+[^>]*itemprop=["'][^"']+["'][^>]*>(?:([\s\S]*?)<\/(?:span|div|p)>)?/gi);
  for (const tag of tags) {
    if (attributeValue(tag[0], "itemprop")?.toLowerCase() !== value.toLowerCase()) continue;
    return attributeValue(tag[0], "content") ?? tagText(tag[0], "span") ?? tagText(tag[0], "div") ?? tagText(tag[0], "p");
  }
  return null;
}

function attributeValue(tag: string, attr: string) {
  const match = tag.match(new RegExp(`${attr}=["']([^"']+)["']`, "i"));
  return match ? decodeHtml(match[1]) : null;
}

function tagText(html: string, tag: string) {
  const match = html.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i"));
  return match ? decodeHtml(match[1].replace(/<[^>]+>/g, " ")) : null;
}

function parseJsonLdObjects(html: string): Record<string, unknown>[] {
  const objects: Record<string, unknown>[] = [];
  const blocks = html.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi);
  for (const block of blocks) {
    try {
      const parsed = JSON.parse(decodeHtml(block[1].trim())) as unknown;
      flattenJsonLd(parsed, objects);
    } catch {
      // Ignore malformed embedded metadata.
    }
  }
  return objects;
}

function flattenJsonLd(value: unknown, objects: Record<string, unknown>[]) {
  if (Array.isArray(value)) {
    value.forEach((item) => flattenJsonLd(item, objects));
    return;
  }
  if (!value || typeof value !== "object") return;
  const record = value as Record<string, unknown>;
  objects.push(record);
  if (Array.isArray(record["@graph"])) record["@graph"].forEach((item) => flattenJsonLd(item, objects));
}

function offerPrices(item: Record<string, unknown>) {
  const offers = item["offers"];
  const values = Array.isArray(offers) ? offers : offers ? [offers] : [];
  return values.flatMap((offer) => {
    if (!offer || typeof offer !== "object") return [];
    const record = offer as Record<string, unknown>;
    return [record["price"], record["lowPrice"], record["highPrice"], record["priceSpecification"]]
      .flatMap((value) => {
        if (value && typeof value === "object" && !Array.isArray(value)) return [(value as Record<string, unknown>)["price"]];
        if (Array.isArray(value)) return value.map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>)["price"] : item));
        return [value];
      })
      .map(stringValue);
  });
}

function breadcrumbCategory(item: Record<string, unknown>) {
  const type = stringValue(item["@type"])?.toLowerCase();
  if (!type?.includes("breadcrumblist")) return null;
  const elements = Array.isArray(item["itemListElement"]) ? item["itemListElement"] : [];
  const names = elements
    .map((element) => (element && typeof element === "object" ? stringValue((element as Record<string, unknown>)["name"]) : null))
    .filter((name): name is string => Boolean(name));
  return names.at(-1) ?? null;
}

function firstNumber(values: Array<string | null>) {
  for (const value of values) {
    const cents = priceToCents(value);
    if (cents !== null) return cents;
  }
  return null;
}

function firstString(values: Array<string | null>) {
  return values.find((value): value is string => Boolean(cleanText(value))) ?? null;
}

function stringValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  return null;
}

function imageValue(value: unknown) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return imageValue(value[0]);
  if (value && typeof value === "object") return stringValue((value as Record<string, unknown>)["url"]);
  return null;
}

function priceToCents(value: string | null) {
  if (!value) return null;
  const match = value.replace(/\s/g, "").match(/(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)/);
  if (!match) return null;
  const normalized = normalizePriceNumber(match[1]);
  const euros = Number(normalized);
  return Number.isFinite(euros) ? Math.round(euros * 100) : null;
}

function normalizePriceNumber(value: string) {
  const comma = value.lastIndexOf(",");
  const dot = value.lastIndexOf(".");
  if (comma > dot) return value.replace(/\./g, "").replace(",", ".");
  if (dot > comma) return value.replace(/,/g, "");
  return value.replace(",", ".");
}

function formatEuroInput(cents: number) {
  return (cents / 100).toFixed(2).replace(".", ",");
}

function cleanText(value: string | null) {
  if (!value) return null;
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned || null;
}

function absolutizeUrl(value: string, pageUrl: string) {
  try {
    return new URL(value, pageUrl).toString();
  } catch {
    return null;
  }
}

function decodeHtml(value: string) {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}
