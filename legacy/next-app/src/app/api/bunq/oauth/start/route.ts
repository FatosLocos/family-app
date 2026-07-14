import { randomBytes } from "node:crypto";
import { NextResponse } from "next/server";
import { buildBunqAuthorizationUrl, getBunqConnectionForCurrentUser } from "@/lib/bunq";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const result = await getBunqConnectionForCurrentUser();
  if ("error" in result) {
    return NextResponse.redirect(new URL(`/instellingen?bunq_error=${encodeURIComponent(result.error ?? "bunq is nog niet gekoppeld.")}`, request.url));
  }

  try {
    const state = randomBytes(24).toString("hex");
    const response = NextResponse.redirect(buildBunqAuthorizationUrl(result.connection, url.origin, state));
    response.cookies.set("bunq_oauth_state", state, {
      httpOnly: true,
      sameSite: "lax",
      secure: url.protocol === "https:",
      maxAge: 10 * 60,
      path: "/",
    });
    return response;
  } catch (error) {
    return NextResponse.redirect(
      new URL(`/instellingen?bunq_error=${encodeURIComponent(error instanceof Error ? error.message : "bunq OAuth kon niet starten.")}`, request.url),
    );
  }
}
