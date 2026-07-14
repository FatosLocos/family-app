import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";

export async function getHomeAssistantConfig() {
  const auth = await requireLocalUser();
  if ("error" in auth) return { error: auth.error, status: auth.status };
  const { rows } = await query<{ base_url: string; token: string }>(
    "select base_url, token from home_assistant_config where household_id = $1",
    [localIds.householdId],
  );
  const baseUrl = rows[0]?.base_url ?? process.env.HOME_ASSISTANT_URL;
  const token = rows[0]?.token ?? process.env.HOME_ASSISTANT_TOKEN;
  if (!baseUrl || !token) return { error: "Home Assistant is nog niet gekoppeld.", status: 400 as const };
  return { baseUrl: baseUrl.replace(/\/$/, ""), token };
}

export function serviceForEntity(entityId: string) {
  const domain = entityId.split(".")[0];

  switch (domain) {
    case "light":
    case "switch":
      return { domain, service: "toggle" };
    case "scene":
      return { domain, service: "turn_on" };
    case "script":
      return { domain, service: "turn_on" };
    case "cover":
      return { domain, service: "toggle" };
    case "climate":
      return { domain, service: "toggle" };
    case "media_player":
      return { domain, service: "media_play_pause" };
    default:
      return null;
  }
}
