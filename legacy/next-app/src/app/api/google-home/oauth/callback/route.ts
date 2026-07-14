import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { exchangeNestSdmCode, getGoogleHomeIntegrationForCurrentUser, persistGoogleToken, syncNestSdmDevices } from "@/lib/google-home";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const state = url.searchParams.get("state");
  const code = url.searchParams.get("code");
  const error = url.searchParams.get("error");
  const cookieStore = await cookies();
  const expectedState = cookieStore.get("google_home_oauth_state")?.value;
  const mode = cookieStore.get("google_home_oauth_mode")?.value === "home_apis" ? "home_apis" : "nest_sdm";
  const redirectUrl = new URL("/home", request.url);

  if (error) {
    redirectUrl.searchParams.set("google_home_error", error);
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  if (!state || !expectedState || state !== expectedState || !code) {
    redirectUrl.searchParams.set("google_home_error", "OAuth callback is ongeldig of verlopen.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  const result = await getGoogleHomeIntegrationForCurrentUser(mode);
  if ("error" in result) {
    redirectUrl.searchParams.set("google_home_error", result.error ?? "Google Home is niet gekoppeld.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  try {
    const token = await exchangeNestSdmCode(result.integration, url.origin, code);
    await persistGoogleToken(result.integration.id, token, result.integration.secret_refresh_token);
    const refreshed = await getGoogleHomeIntegrationForCurrentUser(mode);
    if (!("error" in refreshed)) {
      await syncNestSdmDevices(refreshed.integration);
    }
    redirectUrl.searchParams.set("google_home_status", "gekoppeld");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  } catch (caught) {
    redirectUrl.searchParams.set("google_home_error", caught instanceof Error ? caught.message : "OAuth callback mislukt.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }
}

function clearOauthCookies(response: NextResponse) {
  response.cookies.delete("google_home_oauth_state");
  response.cookies.delete("google_home_oauth_mode");
  return response;
}
