import { randomBytes } from "node:crypto";
import { NextResponse } from "next/server";
import { buildNestSdmAuthorizationUrl, getGoogleHomeIntegrationForCurrentUser } from "@/lib/google-home";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const mode = url.searchParams.get("mode") === "home_apis" ? "home_apis" : "nest_sdm";

  if (mode !== "nest_sdm") {
    return NextResponse.redirect(new URL("/home?google_home_error=home_apis_requires_mobile_platform", request.url));
  }

  const result = await getGoogleHomeIntegrationForCurrentUser(mode);
  if ("error" in result) {
    return NextResponse.redirect(new URL(`/home?google_home_error=${encodeURIComponent(result.error ?? "Google Home is niet gekoppeld.")}`, request.url));
  }

  try {
    const state = randomBytes(24).toString("hex");
    const authUrl = buildNestSdmAuthorizationUrl(result.integration, url.origin, state);
    const response = NextResponse.redirect(authUrl);
    response.cookies.set("google_home_oauth_state", state, {
      httpOnly: true,
      sameSite: "lax",
      secure: url.protocol === "https:",
      maxAge: 10 * 60,
      path: "/",
    });
    response.cookies.set("google_home_oauth_mode", mode, {
      httpOnly: true,
      sameSite: "lax",
      secure: url.protocol === "https:",
      maxAge: 10 * 60,
      path: "/",
    });
    return response;
  } catch (error) {
    return NextResponse.redirect(
      new URL(`/home?google_home_error=${encodeURIComponent(error instanceof Error ? error.message : "OAuth start mislukt.")}`, request.url),
    );
  }
}
