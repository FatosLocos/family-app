import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { exchangeBunqOAuthCode, getBunqConnectionForCurrentUser, persistBunqOAuthToken } from "@/lib/bunq";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const redirectUrl = new URL("/instellingen", request.url);
  const state = url.searchParams.get("state");
  const code = url.searchParams.get("code");
  const error = url.searchParams.get("error");
  const cookieStore = await cookies();
  const expectedState = cookieStore.get("bunq_oauth_state")?.value;

  if (error) {
    redirectUrl.searchParams.set("bunq_error", sanitizeError(error));
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  if (!state || !expectedState || state !== expectedState || !code) {
    redirectUrl.searchParams.set("bunq_error", "bunq OAuth callback is ongeldig of verlopen.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  const result = await getBunqConnectionForCurrentUser();
  if ("error" in result) {
    redirectUrl.searchParams.set("bunq_error", result.error ?? "bunq is nog niet gekoppeld.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  try {
    const token = await exchangeBunqOAuthCode(result.connection, url.origin, code);
    await persistBunqOAuthToken(result.connection.id, token);
    redirectUrl.searchParams.set("bunq_status", "oauth_gekoppeld");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  } catch (caught) {
    redirectUrl.searchParams.set("bunq_error", caught instanceof Error ? sanitizeError(caught.message) : "bunq OAuth callback mislukt.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }
}

function clearOauthCookies(response: NextResponse) {
  response.cookies.delete("bunq_oauth_state");
  return response;
}

function sanitizeError(message: string) {
  return message
    .replace(/access_token=[^&\s]+/g, "access_token=[afgeschermd]")
    .replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]")
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]");
}
