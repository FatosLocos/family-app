export function hasLocalDatabaseEnv() {
  return Boolean(process.env.DATABASE_URL);
}

export function hasBackendEnv() {
  return hasLocalDatabaseEnv();
}

export function hasHueEnv() {
  return Boolean(process.env.HUE_BRIDGE_URL && process.env.HUE_APP_KEY);
}

export function getShoppingPriceProviderStatus() {
  if (process.env.SHOPPING_PRICE_PROVIDER === "none") return { configured: false, id: "none", label: "Geen live provider" };
  if (process.env.PEPESTO_API_KEY) return { configured: true, id: "pepesto", label: "Pepesto" };
  if (process.env.SHOPPING_SCRAPER_API_KEY) return { configured: true, id: "shopping-scraper", label: "ShoppingScraper" };
  if (process.env.APIFY_TOKEN) return { configured: true, id: "checkjebon", label: "Checkjebon + PrijsProfeet + Kaufland test" };
  return { configured: true, id: "checkjebon", label: "Checkjebon + PrijsProfeet" };
}
