import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({
    ok: true,
    app: "family-app",
    timestamp: new Date().toISOString(),
  });
}
