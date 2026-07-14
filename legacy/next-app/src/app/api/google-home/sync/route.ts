import { NextResponse } from "next/server";
import { getGoogleHomeIntegrationForCurrentUser, syncNestSdmDevices } from "@/lib/google-home";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { mode?: string } | null;
  const mode = body?.mode === "nest_sdm" ? "nest_sdm" : "home_apis";
  const result = await getGoogleHomeIntegrationForCurrentUser(mode);

  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  if (mode === "nest_sdm") {
    try {
      const synced = await syncNestSdmDevices(result.integration);
      return NextResponse.json({ ok: true, count: synced.count });
    } catch (error) {
      return NextResponse.json(
        { error: error instanceof Error ? sanitizeError(error.message) : "Nest SDM synchronisatie mislukt." },
        { status: 502 },
      );
    }
  }

  return NextResponse.json(
    {
      error: "Google Home APIs sync vereist nog OAuth/platform flow in een ondersteund Android/iOS traject.",
      next: "Gebruik Home APIs voor structures/devices/automations; voor deze webapp slaan we eerst metadata en consentstatus op.",
    },
    { status: 501 },
  );
}

function sanitizeError(message: string) {
  return message.replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]").replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]");
}
