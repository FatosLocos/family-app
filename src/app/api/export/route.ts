import { NextResponse } from "next/server";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { buildExportPayload } from "@/lib/export";
import { getLocalAppData } from "@/lib/local-db";
import { getLocalUser } from "@/lib/local-auth";

export async function GET() {
  const exportedAt = new Date().toISOString();

  if (hasLocalDatabaseEnv()) {
    const user = await getLocalUser();
    if (!user) return NextResponse.json({ error: "Niet ingelogd." }, { status: 401 });
    return exportResponse(await getLocalAppData(), exportedAt);
  }

  return NextResponse.json({ error: "Export is alleen beschikbaar met PostgreSQL-configuratie." }, { status: 503 });
}

function exportResponse(data: Awaited<ReturnType<typeof getLocalAppData>>, exportedAt: string) {
  const payload = buildExportPayload(data, exportedAt);
  const body = JSON.stringify(payload, null, 2);
  const date = exportedAt.slice(0, 10);
  const safeName = payload.household_name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "huishouden";

  return new NextResponse(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "content-disposition": `attachment; filename="family_app-${safeName}-export-${date}.json"`,
      "cache-control": "no-store",
    },
  });
}
