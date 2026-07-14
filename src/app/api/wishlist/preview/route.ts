import { NextResponse } from "next/server";
import { parseWishlistPreview } from "@/lib/wishlist-preview";

const MAX_HTML_BYTES = 512_000;

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { url?: unknown } | null;
  const rawUrl = typeof body?.url === "string" ? body.url.trim() : "";
  let url: URL;

  try {
    url = new URL(rawUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("unsupported protocol");
  } catch {
    return NextResponse.json({ error: "Gebruik een geldige http(s)-link." }, { status: 400 });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        accept: "text/html,application/xhtml+xml",
        "user-agent": "FamilyApp Wishlist Preview/1.0",
      },
      redirect: "follow",
    });
    if (!response.ok) return NextResponse.json({ error: "Deze link kon niet worden gelezen." }, { status: 502 });

    const html = (await response.text()).slice(0, MAX_HTML_BYTES);
    return NextResponse.json(parseWishlistPreview(html, response.url || url.toString()));
  } catch {
    return NextResponse.json({ error: "Metadata ophalen is niet gelukt." }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }
}
