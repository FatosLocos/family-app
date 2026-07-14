import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  exchangeOutlookCode,
  getOutlookIntegrationForCurrentUser,
  persistOutlookToken,
  fetchOutlookAccountEmail,
  saveOutlookAccountEmail,
  syncOutlookCalendar,
} from "@/lib/outlook-calendar";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const redirectUrl = new URL("/agenda", request.url);
  const state = url.searchParams.get("state");
  const code = url.searchParams.get("code");
  const error = url.searchParams.get("error");
  const cookieStore = await cookies();
  const expectedState = cookieStore.get("outlook_calendar_oauth_state")?.value;
  const codeVerifier = cookieStore.get("outlook_calendar_oauth_verifier")?.value;

  if (error) {
    redirectUrl.searchParams.set("outlook_error", error);
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  if (!state || !expectedState || state !== expectedState || !code || !codeVerifier) {
    redirectUrl.searchParams.set("outlook_error", "Outlook OAuth callback is ongeldig of verlopen.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  const result = await getOutlookIntegrationForCurrentUser();
  if ("error" in result) {
    redirectUrl.searchParams.set("outlook_error", result.error ?? "Outlook agenda is niet gekoppeld.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }

  try {
    const token = await exchangeOutlookCode(result.integration, url.origin, code, codeVerifier);
    await persistOutlookToken(result.integration.id, token, result.integration.secret_refresh_token);
    if (token.access_token) {
      await saveOutlookAccountEmail(result.integration.id, await fetchOutlookAccountEmail(token.access_token));
    }
    const refreshed = await getOutlookIntegrationForCurrentUser();
    if (!("error" in refreshed)) await syncOutlookCalendar(refreshed.integration);
    redirectUrl.searchParams.set("outlook_status", "gekoppeld");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  } catch (caught) {
    redirectUrl.searchParams.set("outlook_error", caught instanceof Error ? sanitizeError(caught.message) : "Outlook callback mislukt.");
    return clearOauthCookies(NextResponse.redirect(redirectUrl));
  }
}

function clearOauthCookies(response: NextResponse) {
  response.cookies.delete("outlook_calendar_oauth_state");
  response.cookies.delete("outlook_calendar_oauth_verifier");
  return response;
}

function sanitizeError(message: string) {
  return message.replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]").replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]");
}
