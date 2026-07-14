import { describe, expect, it } from "vitest";
import { buildBasketPriceComparison } from "@/lib/shopping-price-comparison";
import type { PriceObservation, ShoppingItem } from "@/lib/types";

describe("buildBasketPriceComparison", () => {
  it("compares basket prices per supported store and extracts offers", () => {
    const items: ShoppingItem[] = [
      {
        id: "item-1",
        household_id: "household-1",
        list_id: "list-1",
        product_id: "product-1",
        name: "Halfvolle melk",
        category: "Zuivel",
        quantity: "1 liter",
        checked: false,
      },
    ];
    const observations: PriceObservation[] = [
      price("old-ah", "Halfvolle melk", "AH", "2026-07-12T08:00:00.000Z", 119),
      price("new-ah", "Halfvolle melk", "Albert Heijn", "2026-07-13T08:00:00.000Z", 99, 129, "Bonus"),
      price("jumbo", "Halfvolle melk", "Jumbo", "2026-07-13T07:00:00.000Z", 95),
      price("unknown", "Halfvolle melk", "Onbekend", "2026-07-13T07:00:00.000Z", 10),
    ];

    const comparison = buildBasketPriceComparison(items, observations);

    expect(comparison.openItemCount).toBe(1);
    expect(comparison.bestStore?.storeId).toBe("jumbo");
    expect(comparison.stores.find((store) => store.storeId === "albert-heijn")?.totalCents).toBe(99);
    expect(comparison.stores.find((store) => store.storeId === "jumbo")?.totalCents).toBe(95);
    expect(comparison.offers).toHaveLength(1);
    expect(comparison.offers[0]?.storeLabel).toBe("Albert Heijn");
  });
});

function price(
  id: string,
  productName: string,
  store: string,
  observedAt: string,
  totalPriceCents: number,
  regularPriceCents: number | null = null,
  offerLabel: string | null = null,
): PriceObservation {
  return {
    id,
    household_id: "household-1",
    product_id: "product-1",
    product_name: productName,
    store,
    observed_at: observedAt,
    unit_price_cents: totalPriceCents,
    total_price_cents: totalPriceCents,
    quantity: "1 liter",
    source: "manual",
    regular_price_cents: regularPriceCents,
    offer_label: offerLabel,
    offer_valid_until: null,
    external_url: null,
  };
}
