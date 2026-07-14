import { describe, expect, it, vi } from "vitest";
import { fetchFreeShoppingPrices } from "@/lib/checkjebon-price-provider";
import type { ShoppingItem } from "@/lib/types";

describe("fetchFreeShoppingPrices", () => {
  it("aligns package sizes across stores when Checkjebon has multiple sizes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => [
        {
          n: "ah",
          c: "Albert Heijn",
          u: "https://www.ah.nl/producten/product/",
          d: [
            product("Nutella Hazelnootpasta", "200 g", 3.49),
            product("Nutella Hazelnootpasta", "600 g", 5.99),
            product("Nutella Biscuits", "166 g", 3.19),
          ],
        },
        {
          n: "jumbo",
          c: "Jumbo",
          u: "https://www.jumbo.com/producten/",
          d: [
            product("Nutella 200 g", "200 g", 3.49),
            product("Nutella 600 g", "40 x 15 g", 5.79),
            product("Nutella Hazelnootpasta 350 g", "", 3.99),
          ],
        },
        {
          n: "lidl",
          c: "Lidl",
          u: "https://www.lidl.nl/p/",
          d: [
            product("Nutella", "600 g", 5.49),
            product("Nutella", "825 g", 5.99),
            product("Nutella B-ready", "132 g", 3.49),
          ],
        },
      ],
    } as Response);

    const prices = await fetchFreeShoppingPrices([shoppingItem("Nutella pasta")]);

    expect(prices.map((price) => [price.store, price.quantity, price.productName])).toEqual([
      ["Albert Heijn", "600 g", "Nutella Hazelnootpasta"],
      ["Jumbo", "40 x 15 g", "Nutella 600 g"],
      ["Lidl", "600 g", "Nutella"],
    ]);
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

function product(name: string, size: string, price: number) {
  return { n: name, s: size, p: price, l: name.toLowerCase().replaceAll(" ", "-") };
}
