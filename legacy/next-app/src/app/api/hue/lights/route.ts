import { NextResponse } from "next/server";
import { getHueConfigForCurrentUser, hueRequestJson, mapHueLight } from "@/lib/hue";

export async function GET() {
  const result = await getHueConfigForCurrentUser();
  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  try {
    const response = await hueRequestJson<{ data?: unknown[] }>(`${result.config.bridgeUrl}/clip/v2/resource/light`, {
      headers: { "hue-application-key": result.config.appKey },
    });

    if (!response.ok) {
      return NextResponse.json({ error: "Hue Bridge gaf geen geldige lampstatus terug." }, { status: 502 });
    }

    const payload = response.json;
    const lights = (payload.data ?? []).map((resource) => mapHueLight(resource as Parameters<typeof mapHueLight>[0]));
    return NextResponse.json({ lights });
  } catch {
    return NextResponse.json({ error: "Hue Bridge is niet bereikbaar vanaf deze server." }, { status: 502 });
  }
}
