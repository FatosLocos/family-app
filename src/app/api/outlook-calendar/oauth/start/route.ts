import { createHash, randomBytes } from "node:crypto";
import { NextResponse } from "next/server";
import { buildOutlookAuthorizationUrl, prepareOutlookIntegrationForCurrentUser } from "@/lib/outlook-calendar";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const result = await prepareOutlookIntegrationForCurrentUser();
  if ("error" in result) {
    return NextResponse.redirect(new URL(`/agenda?outlook_error=${encodeURIComponent(result.error ?? "Outlook agenda is niet gekoppeld.")}`, request.url));
  }

  try {
    const state = randomBytes(24).toString("hex");
    const codeVerifier = randomBytes(48).toString("base64url");
    const codeChallenge = createHash("sha256").update(codeVerifier).digest("base64url");
    const response = NextResponse.redirect(buildOutlookAuthorizationUrl(result.integration, url.origin, state, codeChallenge));
    response.cookies.set("outlook_calendar_oauth_state", state, {
      httpOnly: true,
      sameSite: "lax",
      secure: url.protocol === "https:",
      maxAge: 10 * 60,
      path: "/",
    });
    response.cookies.set("outlook_calendar_oauth_verifier", codeVerifier, {
      httpOnly: true,
      sameSite: "lax",
      secure: url.protocol === "https:",
      maxAge: 10 * 60,
      path: "/",
    });
    return response;
  } catch (error) {
    return NextResponse.redirect(
      new URL(`/agenda?outlook_error=${encodeURIComponent(error instanceof Error ? error.message : "Outlook autorisatie kon niet starten.")}`, request.url),
    );
  }
}
