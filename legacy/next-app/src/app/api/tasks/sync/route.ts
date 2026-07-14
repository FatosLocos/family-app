import { NextResponse } from "next/server";
import { getTaskIntegrationForCurrentUser } from "@/lib/task-integrations";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { provider?: string } | null;
  const provider = body?.provider;

  if (provider !== "microsoft_todo" && provider !== "apple_reminders") {
    return NextResponse.json({ error: "Onbekende takenprovider." }, { status: 400 });
  }

  const result = await getTaskIntegrationForCurrentUser(provider);
  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  if (provider === "microsoft_todo") {
    return NextResponse.json(
      {
        error: "Microsoft To Do sync vereist nog Microsoft OAuth token exchange en Graph task list/task calls.",
        next: "Registreer de app in Microsoft Entra, vraag Tasks.ReadWrite consent en implementeer daarna /me/todo/lists en /me/todo/lists/{id}/tasks.",
      },
      { status: 501 },
    );
  }

  return NextResponse.json(
    {
      error: "Apple Herinneringen kan niet rechtstreeks vanaf deze webserver synchroniseren.",
      next: "Gebruik later een native macOS/iOS helper via EventKit die lokaal toestemming vraagt en met deze app synchroniseert.",
    },
    { status: 501 },
  );
}
