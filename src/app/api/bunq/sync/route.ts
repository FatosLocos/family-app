import { NextResponse } from "next/server";
import { getBunqConnectionForCurrentUser, syncBunqConnection } from "@/lib/bunq";

export async function POST() {
  const result = await getBunqConnectionForCurrentUser();
  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  try {
    const sync = await syncBunqConnection(result.connection);
    return NextResponse.json({ ok: true, ...sync });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? sanitizeError(error.message) : "bunq synchronisatie mislukt." },
      { status: 502 },
    );
  }
}

function sanitizeError(message: string) {
  return message
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]")
    .replace(/access_token=[^&\s]+/g, "access_token=[afgeschermd]")
    .replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]");
}
