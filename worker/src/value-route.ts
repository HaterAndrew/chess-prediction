// GET /entry-value: the entry-value figures, for whoever holds the shared key.
//
// The inputs (fees, entry counts) are public; the computed dollar figure is
// kept off the public page and out of the public repo. Gated like the CCA
// proxy: a Worker secret compared in constant time, failing closed when the
// secret is unset, which is every Preview (they get no secrets). Wrong keys
// count against per-IP and global hourly buckets so the key cannot be guessed
// at network speed.
import { timingSafeEqual } from "./cca-proxy";
import type { Env } from "./env";
import { entryValues, type ValuePayload } from "./entry-value";
import { jsonResponse } from "./http";

export const VALUE_KEY_HEADER = "X-Value-Key";
// The link handed to the organizer. It lands on the page's own #value
// unlock (docs/entry_value.js); the hash never reaches the server.
export const PRICE_PATH = "/price";
export const FAIL_LIMIT_PER_IP = 10;
export const FAIL_LIMIT_GLOBAL = 50;

const NO_STORE = { "Cache-Control": "no-store" };

function hourBucket(): number {
  return Math.floor(Date.now() / 3_600_000);
}

function failKeys(request: Request): [string, string] {
  const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
  const hour = hourBucket();
  return [`vf:${ip}:${hour}`, `vf:global:${hour}`];
}

async function count(kv: KVNamespace, key: string): Promise<number> {
  const raw = await kv.get(key);
  return raw ? parseInt(raw, 10) || 0 : 0;
}

async function recordFailure(kv: KVNamespace, keys: string[]): Promise<void> {
  for (const key of keys) {
    await kv.put(key, String((await count(kv, key)) + 1), { expirationTtl: 7200 });
  }
}

async function loadPayload(env: Env): Promise<ValuePayload> {
  // The site data is this Worker's own static asset (see agent.loadData).
  const resp = await env.ASSETS.fetch(new URL("/data/website_data.json", "https://assets.local"));
  if (!resp.ok) throw new Error(`site data fetch failed: ${resp.status}`);
  return (await resp.json()) as ValuePayload;
}

export function priceRedirect(request: Request): Response {
  return new Response(null, {
    status: 302,
    headers: { Location: new URL("/#value", request.url).toString(), "Cache-Control": "no-store" },
  });
}

export async function handleEntryValue(env: Env, request: Request): Promise<Response> {
  const reply = (body: unknown, status: number) =>
    jsonResponse(body, { status, headers: NO_STORE }, env, request);

  if (request.method !== "GET") return reply({ error: "method_not_allowed" }, 405);
  if (!env.ENTRY_VALUE_KEY) return reply({ error: "not_configured" }, 403);
  // An unavailable limiter means guesses cannot be bounded: refuse.
  if (!env.KV) return reply({ error: "limiter_unavailable" }, 503);

  const keys = failKeys(request);
  const [ipFails, globalFails] = await Promise.all(keys.map((k) => count(env.KV!, k)));
  if (ipFails >= FAIL_LIMIT_PER_IP || globalFails >= FAIL_LIMIT_GLOBAL) {
    return reply({ error: "too_many_attempts" }, 429);
  }

  const provided = request.headers.get(VALUE_KEY_HEADER) ?? "";
  if (!provided || !timingSafeEqual(provided, env.ENTRY_VALUE_KEY)) {
    await recordFailure(env.KV, keys);
    return reply({ error: "wrong_key" }, 401);
  }

  try {
    const data = await loadPayload(env);
    return reply({ generated: data.generated, events: entryValues(data) }, 200);
  } catch (err) {
    console.error("entry-value:", err);
    return reply({ error: "data_unavailable" }, 502);
  }
}
