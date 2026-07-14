import Link from "next/link";
import { notFound } from "next/navigation";
import { Check, ExternalLink, Gift, LockKeyhole, ShoppingBag } from "lucide-react";
import { purchasePublicWishlistItem, reservePublicWishlistItem } from "@/app/actions";
import { money } from "@/lib/format";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getPublicWishlistByToken } from "@/lib/local-db";
import type { WishlistItem } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function PublicWishlistPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  if (!hasLocalDatabaseEnv()) notFound();
  const data = await getPublicWishlistByToken(token);
  if (!data) notFound();

  const open = data.items.filter((item) => item.status === "open").length;
  const reserved = data.items.filter((item) => item.status === "reserved").length;
  const purchased = data.items.filter((item) => item.status === "purchased").length;

  return (
    <main className="public-wishlist-shell">
      <section className="public-wishlist-hero">
        <div>
          <span className="eyebrow">Verlanglijst</span>
          <h1>{data.share.title || data.household.name}</h1>
          <p>
            Kies een wens om te reserveren of af te strepen. Je ziet alleen wensen die het gezin bewust openbaar heeft gemaakt.
          </p>
        </div>
        <div className="public-wishlist-stats">
          <PublicStat label="Open" value={open} />
          <PublicStat label="Gereserveerd" value={reserved} />
          <PublicStat label="Afgestreept" value={purchased} />
        </div>
      </section>
      <section className="public-wishlist-list">
        {data.items.length === 0 && (
          <div className="card">
            <h2>Nog geen publieke wensen</h2>
            <p className="muted">De lijst is actief, maar er zijn nog geen wensen openbaar gezet.</p>
          </div>
        )}
        {data.items.map((item) => (
          <PublicWishlistCard item={item} token={token} key={item.id} />
        ))}
      </section>
      <section className="public-wishlist-footer">
        <LockKeyhole size={17} />
        <span>Deze pagina geeft geen toegang tot de gezinsapp, agenda, documenten of financiële gegevens.</span>
        <Link href="/login">Gezinsapp login</Link>
      </section>
    </main>
  );
}

function PublicWishlistCard({ item, token }: { item: WishlistItem; token: string }) {
  return (
    <article className={`public-wishlist-card ${item.status}`}>
      {item.image_url ? (
        <img src={item.image_url} alt="" className="public-wishlist-image" />
      ) : (
        <div className="public-wishlist-image placeholder">
          <Gift size={30} />
        </div>
      )}
      <div className="public-wishlist-body">
        <div className="section-head">
          <div>
            <h2>{item.title}</h2>
            <p className="muted">{[item.desired_by, item.category, item.price_cents ? money(item.price_cents) : null].filter(Boolean).join(" · ")}</p>
          </div>
          <span className={item.status === "open" ? "status" : item.status === "reserved" ? "status accent" : "status muted-status"}>{statusLabel(item.status)}</span>
        </div>
        <div className="tag-list">
          <span className="status">{item.purchase_mode === "repeatable" ? "Meerdere keren mogelijk" : "Eenmalig cadeau"}</span>
          {item.purchase_count > 0 && <span className="status accent">{item.purchase_count}x gekocht</span>}
        </div>
        {item.description && <p className="public-wishlist-description">{item.description}</p>}
        <div className="public-wishlist-actions">
          {item.url && (
            <a className="button" href={item.url} target="_blank" rel="noreferrer">
              <ExternalLink size={17} /> Bekijk link
            </a>
          )}
          {item.status === "open" && item.purchase_mode !== "repeatable" && (
            <form action={reservePublicWishlistItem} className="public-reserve-form">
              <input type="hidden" name="token" value={token} />
              <input type="hidden" name="id" value={item.id} />
              <input name="name" required placeholder="Jouw naam" aria-label="Jouw naam" />
              <button className="button primary">
                <ShoppingBag size={17} /> Reserveren
              </button>
            </form>
          )}
          {item.status !== "purchased" && (
            <form action={purchasePublicWishlistItem} className="public-reserve-form">
              <input type="hidden" name="token" value={token} />
              <input type="hidden" name="id" value={item.id} />
              {item.status === "open" && <input name="name" placeholder="Jouw naam" aria-label="Jouw naam" />}
              <button className="button">
                <Check size={17} /> {item.purchase_mode === "repeatable" ? "Ik koop dit ook" : "Afstrepen"}
              </button>
            </form>
          )}
          {item.reserved_by_name && <span className="status accent">Opgepakt door {item.reserved_by_name}</span>}
        </div>
      </div>
    </article>
  );
}

function PublicStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function statusLabel(status: string) {
  if (status === "reserved") return "Gereserveerd";
  if (status === "purchased") return "Afgestreept";
  return "Open";
}
