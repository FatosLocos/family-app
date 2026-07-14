import { NextResponse } from "next/server";
import { getOutlookIntegrationForCurrentUser, syncOutlookCalendar } from "@/lib/outlook-calendar";

export async function POST() {
  const result = await getOutlookIntegrationForCurrentUser();
  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  try {
    const synced = await syncOutlookCalendar(result.integration);
    return NextResponse.json({ ok: true, count: synced.count, calendarCount: synced.calendarCount });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? sanitizeError(error.message) : "Outlook synchronisatie mislukt." },
      { status: 502 },
    );
  }
}

function sanitizeError(message: string) {
  return message.replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [afgeschermd]").replace(/client_secret=[^&\s]+/g, "client_secret=[afgeschermd]");
}
