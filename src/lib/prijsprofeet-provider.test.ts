import { describe, expect, it, vi } from "vitest";
import { fetchPrijsProfeetOffers } from "@/lib/prijsprofeet-provider";
import type { ShoppingItem } from "@/lib/types";

describe("fetchPrijsProfeetOffers", () => {
  it("does not treat derived products as an offer for a loose product", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          offer("AH Rauwkost komkommer", "albert_heijn", 2, 2.49),
          offer("Jumbo Komkommer Salade 200 g", "jumbo", 2.25, 2.29),
          offer("Dove Anti-transpirant roller komkommer", "albert_heijn", 2.89, 5.79, "drogisterij"),
        ],
      }),
    } as Response);

    const offers = await fetchPrijsProfeetOffers([shoppingItem("Komkommer")]);

    expect(offers).toEqual([]);
    fetchMock.mockRestore();
  });

  it("allows exact loose product offers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          offer("AH Komkommer", "albert_heijn", 0.79, 0.99),
          offer("Jumbo Komkommers", "jumbo", 0.89, 1.09),
        ],
      }),
    } as Response);

    const offers = await fetchPrijsProfeetOffers([shoppingItem("Komkommer")]);

    expect(offers.map((item) => item.matchedProductName)).toEqual(["AH Komkommer", "Jumbo Komkommers"]);
    fetchMock.mockRestore();
  });
});

function shoppingItem(name: string): ShoppingItem {
  return {
    id: `item-${name}`,
    household_id: "household",
    list_id: "list",
    product_id: null,
    name,
    category: null,
    quantity: null,
    checked: false,
  };
}

function offer(name: string, retailer: string, price: number, originalPrice: number, category = "groente-fruit") {
  return {
    name,
    retailer,
    price,
    original_price: originalPrice,
    product_url: "https://example.test/product",
    is_promotional: true,
    promotional_keywords: ["ACTIE"],
    promotion_type: "feed",
    valid_until: "2026-07-19",
    score: 100,
    unified_category: category,
  };
}
