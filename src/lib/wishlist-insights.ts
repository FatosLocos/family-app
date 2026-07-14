import type { AppData, WishlistItem } from "@/lib/types";

export type WishlistInsight = {
  total: number;
  publicCount: number;
  openCount: number;
  reservedCount: number;
  purchasedCount: number;
  shareEnabled: boolean;
  shareUrl: string | null;
  nextAction: {
    title: string;
    detail: string;
    href: string;
    done: boolean;
  };
};

export function buildWishlistInsight(data: AppData, origin?: string): WishlistInsight {
  const total = data.wishlistItems.length;
  const publicCount = data.wishlistItems.filter((item) => item.is_public).length;
  const openCount = data.wishlistItems.filter((item) => item.status === "open").length;
  const reservedCount = data.wishlistItems.filter((item) => item.status === "reserved").length;
  const purchasedCount = data.wishlistItems.filter((item) => item.status === "purchased").length;
  const share = data.wishlistShares.find((item) => item.enabled) ?? data.wishlistShares[0] ?? null;
  const shareUrl = share && origin ? `${origin}/wishlist/${share.public_token}` : share ? `/wishlist/${share.public_token}` : null;

  return {
    total,
    publicCount,
    openCount,
    reservedCount,
    purchasedCount,
    shareEnabled: Boolean(share?.enabled),
    shareUrl,
    nextAction: nextWishlistAction(data.wishlistItems, Boolean(share?.enabled)),
  };
}

function nextWishlistAction(items: WishlistItem[], shareEnabled: boolean) {
  if (items.length === 0) {
    return {
      title: "Voeg je eerste wens toe",
      detail: "Leg cadeauwensen, links, budget en voor wie het is vast.",
      href: "/wishlist",
      done: false,
    };
  }
  if (!items.some((item) => item.is_public)) {
    return {
      title: "Maak wensen extern zichtbaar",
      detail: "Zet minimaal een wens op openbaar voordat je de link deelt.",
      href: "/wishlist",
      done: false,
    };
  }
  if (!shareEnabled) {
    return {
      title: "Activeer de deel-link",
      detail: "Maak een publieke wishlist-link voor familie of vrienden.",
      href: "/wishlist",
      done: false,
    };
  }
  return {
    title: "Wishlist klaar om te delen",
    detail: "Externen kunnen open wensen reserveren of afstrepen zonder login.",
    href: "/wishlist",
    done: true,
  };
}
