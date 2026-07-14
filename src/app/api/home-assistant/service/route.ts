import { NextResponse } from "next/server";
import { getHomeAssistantConfig, serviceForEntity } from "@/lib/home-assistant";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { entity_id?: string } | null;
  const entityId = body?.entity_id;

  if (!entityId) {
    return NextResponse.json({ error: "Geen apparaat gekozen." }, { status: 400 });
  }

  const service = serviceForEntity(entityId);
  if (!service) {
    return NextResponse.json({ error: "Deze entiteit kan alleen worden bekeken." }, { status: 400 });
  }

  const config = await getHomeAssistantConfig();
  if ("error" in config) {
    return NextResponse.json({ error: config.error }, { status: config.status });
  }

  try {
    const response = await fetch(`${config.baseUrl}/api/services/${service.domain}/${service.service}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ entity_id: entityId }),
    });

    if (!response.ok) {
      return NextResponse.json({ error: "Home Assistant kon de actie niet uitvoeren." }, { status: 502 });
    }

    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "Home Assistant is niet bereikbaar." }, { status: 502 });
  }
}
