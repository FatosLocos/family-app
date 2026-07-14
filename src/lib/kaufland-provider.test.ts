import { describe, expect, it } from "vitest";
import { bestKauflandMatch } from "@/lib/kaufland-provider";

describe("bestKauflandMatch", () => {
  it("selects a direct product match", () => {
    const match = bestKauflandMatch(
      [
        { title: "K-Classic Salatgurke", price: "0,79 €", unit: "1 stuk", url: "https://kaufland.example/gurke" },
        { title: "Gurkensticks mit Dip", price: "1,99 €", unit: "250 g" },
      ],
      "komkommer",
    );

    expect(match).toMatchObject({
      name: "K-Classic Salatgurke",
      totalPriceCents: 79,
      quantity: "1 stuk",
      externalUrl: "https://kaufland.example/gurke",
    });
  });

  it("does not match unrelated product descriptions", () => {
    const match = bestKauflandMatch(
      [
        { title: "Gurkensticks mit Dip", price: "1,99 €" },
        { title: "Duschgel Gurke Frische", price: "2,49 €" },
      ],
      "komkommer",
    );

    expect(match).toBeNull();
  });
});
