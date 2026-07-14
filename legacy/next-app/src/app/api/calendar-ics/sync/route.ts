import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { getIcsSubscriptionForCurrentUser, markIcsSyncError, syncIcsCalendar } from "@/lib/ics-calendar";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const id = typeof body.id === "string" ? body.id : "";
  if (!id) return NextResponse.json({ error: "ICS-abonnement ontbreekt." }, { status: 400 });
  const result = await getIcsSubscriptionForCurrentUser(id);
  if ("error" in result) return NextResponse.json({ error: result.error }, { status: result.status });
  try {
    const synced = await syncIcsCalendar(result.subscription);
    revalidatePath("/agenda");
    return NextResponse.json({ ok: true, count: synced.count });
  } catch (error) {
    await markIcsSyncError(id);
    return NextResponse.json({ error: error instanceof Error ? sanitizeError(error.message) : "ICS synchronisatie mislukt." }, { status: 502 });
  }
}

function sanitizeError(message: string) {
  return message.replace(/https?:\/\/[^\s]+/g, "ICS-feed [afgeschermd]");
}
