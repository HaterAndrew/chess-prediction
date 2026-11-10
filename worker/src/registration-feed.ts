import { timingSafeEqual } from "./cca-proxy";
import { boundedText } from "./finance/client";
import type { RegistrationCard } from "./finance/registrations";
import type { Env } from "./env";

// Only aggregate counts and registration dates cross the private binding.
// Authentication reuses the existing CI proxy credential; no public selector.
export async function handleRegistrationFeed(env: Env, request: Request): Promise<Response> {
  const reply = (value: unknown, status: number) => Response.json(value, { status, headers: { "Cache-Control": "no-store" } });
  if (request.method !== "GET") return reply({ error: "method_not_allowed" }, 405);
  const key = request.headers.get("X-Proxy-Key");
  if (!env.CCA_PROXY_KEY || !key || !timingSafeEqual(key, env.CCA_PROXY_KEY)) return reply({ error: "forbidden" }, 403);
  if (!env.FINANCE) return reply({ error: "not_configured" }, 503);
  try {
    const asset = await env.ASSETS.fetch(new URL("/data/website_data.json", "https://assets.local"));
    if (!asset.ok) throw new Error("asset_unavailable");
    const data = JSON.parse(await boundedText(asset));
    if (data.is_stale || !Array.isArray(data.tournaments) || data.tournaments.length > 2000) throw new Error("asset_invalid");
    const cards: RegistrationCard[] = data.tournaments.map((t: RegistrationCard) => ({
      family: t.family, year: t.year, status: t.status, event_start: t.event_start, event_end: t.event_end,
    }));
    return reply(await env.FINANCE.registrations(cards), 200);
  } catch {
    console.error(JSON.stringify({ event: "registration_feed_failed", reason: "data_unavailable" }));
    return reply({ error: "data_unavailable" }, 502);
  }
}
