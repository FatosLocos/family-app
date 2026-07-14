import { describe, expect, it } from "vitest";
import { parseWishlistPreview } from "@/lib/wishlist-preview";

describe("parseWishlistPreview", () => {
  it("reads product metadata from open graph and product tags", () => {
    const preview = parseWishlistPreview(
      `
        <html>
          <head>
            <meta property="og:title" content="Nintendo eShop kaart">
            <meta property="og:image" content="/kaart.jpg">
            <meta property="product:price:amount" content="25.00">
            <meta property="product:category" content="Cadeaubonnen">
          </head>
        </html>
      `,
      "https://shop.example.test/product",
    );

    expect(preview).toMatchObject({
      title: "Nintendo eShop kaart",
      image_url: "https://shop.example.test/kaart.jpg",
      category: "Cadeaubonnen",
      price_cents: 2500,
      price: "25,00",
    });
  });

  it("falls back to json-ld offers and breadcrumbs", () => {
    const preview = parseWishlistPreview(
      `
        <script type="application/ld+json">
          {
            "@graph": [
              {"@type": "Product", "name": "LEGO bloemen", "image": "https://cdn.example.test/lego.jpg", "offers": {"price": "49,95"}},
              {"@type": "BreadcrumbList", "itemListElement": [{"name": "Speelgoed"}, {"name": "Bouwsets"}]}
            ]
          }
        </script>
      `,
      "https://shop.example.test/lego",
    );

    expect(preview.title).toBe("LEGO bloemen");
    expect(preview.image_url).toBe("https://cdn.example.test/lego.jpg");
    expect(preview.category).toBe("Bouwsets");
    expect(preview.price_cents).toBe(4995);
  });

  it("reads common webshop price variants", () => {
    const preview = parseWishlistPreview(
      `
        <meta name="price" content="€ 1.249,00">
        <span itemprop="price">1299,95</span>
      `,
      "https://shop.example.test/item",
    );

    expect(preview.price_cents).toBe(124900);
    expect(preview.price).toBe("1249,00");
  });

  it("reads nested json-ld price specifications", () => {
    const preview = parseWishlistPreview(
      `
        <script type="application/ld+json">
          {"@type": "Product", "name": "Cadeaukaart", "offers": {"priceSpecification": {"price": "15"}}}
        </script>
      `,
      "https://shop.example.test/card",
    );

    expect(preview.price_cents).toBe(1500);
  });
});
