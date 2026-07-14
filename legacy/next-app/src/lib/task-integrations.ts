import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";

export async function getTaskIntegrationForCurrentUser(provider: string) {
  const auth = await requireLocalUser();
  if ("error" in auth) return { error: auth.error, status: auth.status };
  const { rows } = await query(
    `select id, provider, status, sync_direction, client_id, tenant_id
     from task_integrations
     where household_id = $1 and provider = $2`,
    [localIds.householdId, provider],
  );
  if (!rows[0]) return { error: "Deze takenkoppeling is nog niet ingesteld.", status: 400 as const };
  return { integration: rows[0] };
}
