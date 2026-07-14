import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildWishlistInsight } from "@/lib/wishlist-insights";

describe("buildWishlistInsight", () => {
  it("summarizes wishlist status and share URL", () => {
    const insight = buildWishlistInsight(demoData, "https://app.example.test");

    expect(insight.total).toBe(demoData.wishlistItems.length);
    expect(insight.publicCount).toBe(2);
    expect(insight.reservedCount).toBe(1);
    expect(insight.shareUrl).toBe("https://app.example.test/wishlist/demo-wishlist");
    expect(insight.nextAction.done).toBe(true);
  });

  it("asks for public items before sharing is complete", () => {
    const insight = buildWishlistInsight({
      ...demoData,
      wishlistItems: demoData.wishlistItems.map((item) => ({ ...item, is_public: false })),
      wishlistShares: [],
    });

    expect(insight.nextAction.title).toBe("Maak wensen extern zichtbaar");
    expect(insight.shareEnabled).toBe(false);
  });
});
