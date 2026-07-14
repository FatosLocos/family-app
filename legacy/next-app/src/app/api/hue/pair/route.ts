import { NextResponse } from "next/server";
import { hueRequestJson } from "@/lib/hue";

export async function POST(request: Request) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Hue pairing is alleen beschikbaar in development." }, { status: 403 });
  }

  const body = (await request.json().catch(() => null)) as { bridge_url?: string; app_name?: string } | null;
  const bridgeUrl = body?.bridge_url?.replace(/\/$/, "");

  if (!bridgeUrl) {
    return NextResponse.json({ error: "bridge_url is verplicht." }, { status: 400 });
  }

  try {
    const response = await hueRequestJson(`${bridgeUrl}/api`, {
      method: "POST",
      body: { devicetype: body?.app_name ?? "family-app#codex" },
    });

    return NextResponse.json({
      result: response.json,
      next: "Als de bridge-knop net is ingedrukt, staat de app key in result[0].success.username. Zet die als HUE_APP_KEY in .env.local.",
    });
  } catch {
    return NextResponse.json({ error: "Hue Bridge is niet bereikbaar op deze URL." }, { status: 502 });
  }
}
