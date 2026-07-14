import { redirect } from "next/navigation";
import { headers } from "next/headers";
import Link from "next/link";
import { Copy, ExternalLink, Gift, Share2, Users } from "lucide-react";
import { ensureWishlistShare, toggleWishlistShare } from "@/app/actions";
import { AppShell } from "@/components/app-shell";
import { CompactModuleHeader } from "@/components/compact-module-header";
import { ModuleLayout } from "@/components/module-layout";
import { WishlistItemForm } from "@/components/forms";
import { WishlistItemList } from "@/components/module-lists";
import { demoData } from "@/lib/demo-data";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { money } from "@/lib/format";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";
import { getAppData, getUser } from "@/lib/local-data";
import type { AppData } from "@/lib/types";
import { buildWishlistInsight } from "@/lib/wishlist-insights";

export const dynamic = "force-dynamic";

export default async function WishlistPage({ searchParams }: { searchParams?: Promise<{ voor?: string }> }) {
  const origin = await requestOrigin();
  const selectedOwner = normalizeSelectedOwner((await searchParams)?.voor);
  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) redirect("/login");
    return <WishlistContent data={await getLocalAppData()} origin={origin} selectedOwner={selectedOwner} />;
  }
  if (!hasLocalDatabaseEnv()) return <WishlistContent data={demoData} origin={origin} selectedOwner={selectedOwner} demo />;
  const user = await getUser();
  if (!user) redirect("/login");
  const data = await getAppData(user.id);
  if (!data) redirect("/");
  return <WishlistContent data={data} origin={origin} selectedOwner={selectedOwner} />;
}

function WishlistContent({ data, origin, selectedOwner, demo = false }: { data: AppData; origin: string; selectedOwner: string | null; demo?: boolean }) {
  const insight = buildWishlistInsight(data, origin);
  const activeShare = data.wishlistShares.find((share) => share.enabled) ?? data.wishlistShares[0] ?? null;
  const shareUrl = activeShare ? `${origin}/wishlist/${activeShare.public_token}` : null;
  const estimatedOpenValue = data.wishlistItems
    .filter((item) => item.status === "open")
    .reduce((sum, item) => sum + (item.price_cents ?? 0), 0);
  const ownerOptions = wishlistOwnerOptions(data);
  const activeOwner = selectedOwner && ownerOptions.some((option) => option.value === selectedOwner) ? selectedOwner : "all";
  const visibleData =
    activeOwner === "all"
      ? data
      : {
          ...data,
          wishlistItems: data.wishlistItems.filter((item) => wishlistOwnerValue(item.desired_by) === activeOwner),
        };

  return (
    <AppShell demo={demo}>
      <ModuleLayout
        className="wishlist-layout"
        asideLabel="Wishlist-acties"
        aside={<WishlistSidePanel data={data} demo={demo} activeOwner={activeOwner} ownerOptions={ownerOptions} insight={insight} activeShare={activeShare} shareUrl={shareUrl} />}
      >
        <div className="module-content-stack">
          <CompactModuleHeader eyebrow="Gezinswensen" title="Wishlist" stats={[{ label: "open", value: insight.openCount }, { label: "gereserveerd", value: insight.reservedCount }, { label: "afgestreept", value: insight.purchasedCount }, { label: "open waarde", value: money(estimatedOpenValue) }]} />
          <WishlistItemList data={visibleData} readOnly={demo} />
        </div>
      </ModuleLayout>
    </AppShell>
  );
}

function WishlistSidePanel({
  data,
  demo,
  activeOwner,
  ownerOptions,
  insight,
  activeShare,
  shareUrl,
}: {
  data: AppData;
  demo: boolean;
  activeOwner: string;
  ownerOptions: ReturnType<typeof wishlistOwnerOptions>;
  insight: ReturnType<typeof buildWishlistInsight>;
  activeShare: AppData["wishlistShares"][number] | null;
  shareUrl: string | null;
}) {
  return (
    <>
      {demo ? (
        <div className="card">
          <h2>Demo-modus</h2>
          <p className="muted">Log in met lokale databaseconfiguratie om wensen echt te beheren en extern te delen.</p>
        </div>
      ) : (
        <WishlistItemForm members={data.members} />
      )}
      <div className="wishlist-control-grid">
        <section className="wishlist-filter-card card">
          <div className="section-head compact">
            <div>
              <span className="eyebrow">Weergave</span>
              <h2>Wishlist kiezen</h2>
            </div>
            <span className="summary-icon"><Users size={18} /></span>
          </div>
          <div className="wishlist-owner-tabs" aria-label="Wishlist filteren op gezinslid">
            <Link className={activeOwner === "all" ? "active" : ""} href="/wishlist">
              Iedereen <span>{data.wishlistItems.length}</span>
            </Link>
            {ownerOptions.map((option) => (
              <Link className={activeOwner === option.value ? "active" : ""} href={`/wishlist?voor=${encodeURIComponent(option.value)}`} key={option.value}>
                {option.label} <span>{option.count}</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="wishlist-control card">
          <div className="section-head compact">
            <div>
              <span className="eyebrow">Extern delen</span>
              <h2>Publiceren</h2>
            </div>
            <span className="summary-icon"><Gift size={18} /></span>
          </div>
          <div className="wishlist-share-box">
            <strong>{insight.nextAction.title}</strong>
            <p className="muted">{insight.nextAction.detail}</p>
            {shareUrl ? (
              <div className="invite-link-box"><Copy size={15} /><span>{shareUrl}</span></div>
            ) : (
              <p className="muted">Maak eerst een deel-link aan. Daarna kun je wensen individueel openbaar zetten.</p>
            )}
          </div>
          <div className="wishlist-share-actions">
            {!demo && !activeShare && (
              <form action={ensureWishlistShare}>
                <button className="button primary"><Share2 size={17} /> Deel-link maken</button>
              </form>
            )}
            {!demo && activeShare && (
              <form action={toggleWishlistShare}>
                <input type="hidden" name="id" value={activeShare.id} />
                <input type="hidden" name="enabled" value={String(activeShare.enabled)} />
                <button className={activeShare.enabled ? "button danger" : "button primary"}>{activeShare.enabled ? "Link pauzeren" : "Link activeren"}</button>
              </form>
            )}
            {shareUrl && <Link className="button" href={`/wishlist/${activeShare?.public_token}`}><ExternalLink size={17} /> Publieke pagina</Link>}
          </div>
        </section>
      </div>
    </>
  );
}

async function requestOrigin() {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const proto = requestHeaders.get("x-forwarded-proto") ?? (host.includes("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

function wishlistOwnerOptions(data: AppData) {
  const counts = new Map<string, { label: string; value: string; count: number }>();
  const preferredLabels = [
    "Huishouden",
    ...data.members.map((member) => member.profile?.full_name ?? member.profile?.email ?? "Gezinslid"),
  ];

  for (const label of preferredLabels) {
    const value = wishlistOwnerValue(label === "Huishouden" ? null : label);
    counts.set(value, { label, value, count: 0 });
  }
  for (const item of data.wishlistItems) {
    const label = item.desired_by?.trim() || "Huishouden";
    const value = wishlistOwnerValue(item.desired_by);
    const existing = counts.get(value);
    counts.set(value, { label: existing?.label ?? label, value, count: (existing?.count ?? 0) + 1 });
  }

  return [...counts.values()].filter((option) => option.count > 0 || option.label !== "Huishouden");
}

function wishlistOwnerValue(owner: string | null) {
  return owner?.trim() || "Huishouden";
}

function normalizeSelectedOwner(owner: string | undefined) {
  if (!owner || owner === "all") return null;
  return owner.trim() || null;
}
