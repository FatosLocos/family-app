import type { HueLight } from "@/lib/types";
import { localIds, query } from "@/lib/local-db";
import { requireLocalUser } from "@/lib/local-auth";
import http from "node:http";
import https from "node:https";

type HueLightResource = {
  id: string;
  metadata?: { name?: string };
  on?: { on?: boolean };
  dimming?: { brightness?: number };
  owner?: { rid?: string };
};

export async function getHueConfigForCurrentUser() {
  const auth = await requireLocalUser();
  if ("error" in auth) return { error: auth.error, status: auth.status };
  const { rows } = await query<{ bridge_url: string; app_key: string }>("select bridge_url, app_key from hue_config where household_id = $1", [
    localIds.householdId,
  ]);
  const bridgeUrl = rows[0]?.bridge_url ?? process.env.HUE_BRIDGE_URL;
  const appKey = rows[0]?.app_key ?? process.env.HUE_APP_KEY;
  if (!bridgeUrl || !appKey) return { error: "Philips Hue is nog niet gekoppeld.", status: 400 as const };
  return {
    config: {
      householdId: localIds.householdId,
      bridgeUrl: bridgeUrl.replace(/\/$/, ""),
      appKey,
    },
  };
}

export function mapHueLight(resource: HueLightResource): HueLight {
  return {
    id: resource.id,
    rid: resource.id,
    name: resource.metadata?.name ?? resource.id,
    on: Boolean(resource.on?.on),
    brightness: typeof resource.dimming?.brightness === "number" ? Math.round(resource.dimming.brightness) : null,
    room: resource.owner?.rid ?? null,
  };
}

export async function hueRequestJson<T>(
  url: string,
  options: {
    method?: "GET" | "POST" | "PUT";
    headers?: Record<string, string>;
    body?: unknown;
  } = {},
) {
  const parsed = new URL(url);
  const body = options.body === undefined ? undefined : JSON.stringify(options.body);
  const transport = parsed.protocol === "https:" ? https : http;

  return new Promise<{ ok: boolean; status: number; json: T }>((resolve, reject) => {
    const request = transport.request(
      parsed,
      {
        method: options.method ?? "GET",
        headers: {
          Accept: "application/json",
          ...(body ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body).toString() } : {}),
          ...options.headers,
        },
        rejectUnauthorized: false,
      },
      (response) => {
        const chunks: Buffer[] = [];
        response.on("data", (chunk: Buffer) => chunks.push(chunk));
        response.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          resolve({
            ok: Boolean(response.statusCode && response.statusCode >= 200 && response.statusCode < 300),
            status: response.statusCode ?? 0,
            json: (text ? JSON.parse(text) : {}) as T,
          });
        });
      },
    );

    request.on("error", reject);
    request.setTimeout(5000, () => request.destroy(new Error("Hue request timeout")));
    if (body) request.write(body);
    request.end();
  });
}
