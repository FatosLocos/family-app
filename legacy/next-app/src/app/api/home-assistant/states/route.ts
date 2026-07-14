import { NextResponse } from "next/server";
import { getHomeAssistantConfig } from "@/lib/home-assistant";

export async function GET() {
  const config = await getHomeAssistantConfig();
  if ("error" in config) {
    return NextResponse.json({ error: config.error }, { status: config.status });
  }

  try {
    const response = await fetch(`${config.baseUrl}/api/states`, {
      headers: { Authorization: `Bearer ${config.token}` },
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.json({ error: "Home Assistant gaf geen geldige status terug." }, { status: 502 });
    }

    const entities = await response.json();
    return NextResponse.json({ entities });
  } catch {
    return NextResponse.json({ error: "Home Assistant is niet bereikbaar." }, { status: 502 });
  }
}
