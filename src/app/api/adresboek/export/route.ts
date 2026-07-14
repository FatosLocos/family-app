import { NextResponse } from "next/server";
import { exportAddressBookVCard } from "@/lib/address-book";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!hasLocalDatabaseEnv()) return NextResponse.json({ error: "Lokale database ontbreekt." }, { status: 503 });
  const user = await getLocalUser();
  if (!user) return NextResponse.json({ error: "Niet ingelogd." }, { status: 401 });
  const data = await getLocalAppData();
  const fileName = `adresboek-${data.household.name.toLowerCase().replace(/[^a-z0-9]+/gi, "-").replace(/(^-|-$)/g, "") || "gezin"}.vcf`;
  return new NextResponse(exportAddressBookVCard(data.householdContacts, data.householdContactMembers ?? []), {
    headers: {
      "content-disposition": `attachment; filename="${fileName}"`,
      "content-type": "text/vcard; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
