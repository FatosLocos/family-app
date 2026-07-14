import { NextResponse } from "next/server";
import { getHueConfigForCurrentUser, hueRequestJson } from "@/lib/hue";

export async function PUT(request: Request, { params }: { params: Promise<{ rid: string }> }) {
  const { rid } = await params;
  const body = (await request.json().catch(() => null)) as { on?: boolean; brightness?: number } | null;
  const result = await getHueConfigForCurrentUser();

  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  const payload: { on?: { on: boolean }; dimming?: { brightness: number } } = {};
  if (typeof body?.on === "boolean") payload.on = { on: body.on };
  if (typeof body?.brightness === "number") payload.dimming = { brightness: Math.max(1, Math.min(100, body.brightness)) };

  if (!payload.on && !payload.dimming) {
    return NextResponse.json({ error: "Geen Hue actie opgegeven." }, { status: 400 });
  }

  try {
    const response = await hueRequestJson(`${result.config.bridgeUrl}/clip/v2/resource/light/${rid}`, {
      method: "PUT",
      headers: {
        "hue-application-key": result.config.appKey,
      },
      body: payload,
    });

    if (!response.ok) {
      return NextResponse.json({ error: "Hue Bridge kon de actie niet uitvoeren." }, { status: 502 });
    }

    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "Hue Bridge is niet bereikbaar vanaf deze server." }, { status: 502 });
  }
}
