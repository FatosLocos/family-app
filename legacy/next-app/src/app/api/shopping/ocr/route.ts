import { NextResponse } from "next/server";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";

const supportedTypes = new Set(["image/jpeg", "image/png", "image/webp", "application/pdf"]);

export async function POST(request: Request) {
  if (!hasLocalDatabaseEnv()) return NextResponse.json({ error: "PostgreSQL is niet geconfigureerd." }, { status: 503 });
  return createLocalShoppingScan(request);
}

async function createLocalShoppingScan(request: Request) {
  const auth = await requireLocalUser();
  if ("error" in auth) return NextResponse.json({ error: auth.error }, { status: auth.status });

  const formData = await request.formData().catch(() => null);
  const file = formData?.get("file");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Upload een foto of PDF van een bon." }, { status: 400 });
  }

  if (!supportedTypes.has(file.type)) {
    return NextResponse.json({ error: "Ondersteund: JPG, PNG, WebP of PDF." }, { status: 400 });
  }

  const { rows } = await query<{ id: string; status: string; source_filename: string | null }>(
    `insert into shopping_scans (household_id, status, source_filename, extracted_text)
     values ($1, 'queued', $2, null)
     returning id, status, source_filename`,
    [localIds.householdId, file.name],
  );

  return NextResponse.json(
    {
      scan: rows[0],
      next: "OCR-provider nog koppelen. Deze route valideert upload en maakt een scanrecord klaar voor herkenning en review.",
    },
    { status: 202 },
  );
}
