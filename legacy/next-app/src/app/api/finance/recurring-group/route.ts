import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { hasLocalDatabaseEnv } from "@/lib/env";
import { localIds, query } from "@/lib/local-db";

const validGroupIds = ["fixed", "insurance", "credit", "subscription", "tax", "other"];

export async function POST(request: Request) {
  const payload = await request.json().catch(() => null);
  const ruleKey = typeof payload?.rule_key === "string" ? payload.rule_key : "";
  const label = typeof payload?.label === "string" ? payload.label : "";
  const groupId = typeof payload?.group_id === "string" ? payload.group_id : "";
  if (!ruleKey || !label || !validGroupIds.includes(groupId)) {
    return NextResponse.json({ error: "Ongeldige terugkerende-kosten groep." }, { status: 400 });
  }

  if (!hasLocalDatabaseEnv()) return NextResponse.json({ error: "PostgreSQL is niet geconfigureerd." }, { status: 503 });
  await query(
      `insert into recurring_transaction_rules (household_id, rule_key, label, action, group_id, updated_at)
       values ($1, $2, $3, 'group_recurring', $4, now())
       on conflict (household_id, rule_key) do update set
         label = excluded.label,
         group_id = excluded.group_id,
         action = case
           when recurring_transaction_rules.action = 'force_recurring' then 'force_recurring'
           else 'group_recurring'
         end,
         updated_at = now()`,
      [localIds.householdId, ruleKey, label, groupId],
  );
  revalidatePath("/geld");
  return NextResponse.json({ ok: true });
}
