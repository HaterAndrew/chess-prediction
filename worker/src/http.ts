// CORS + JSON response helpers (index.ts, verbatim; W1).
import type { Env } from "./env";

const LOCAL_ORIGIN_RE = /^http:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$/i;

function allowlist(env: Env): string[] {
  return env.ALLOWED_ORIGIN.split(",").map((s) => s.trim()).filter(Boolean);
}

export function pickAllowedOrigin(env: Env, request: Request): string {
  const allow = allowlist(env);
  const origin = request.headers.get("Origin");
  if (!origin) return allow[0] ?? "https://haterandrew.github.io";
  if (allow.includes(origin)) return origin;
  if (LOCAL_ORIGIN_RE.test(origin)) return origin;
  return allow[0] ?? "https://haterandrew.github.io";
}

// Authorization, as opposed to pickAllowedOrigin's choice of response header.
//
// 2026-09-07 review: /ask parsed any body it was handed and never consulted
// Origin for permission, so any page could POST a CORS-safelisted `text/plain`
// body, fire no preflight, and run the model on the operator's key. The
// attacker never needs to read the response, and every visitor to their page is
// a different source IP, which is what made the per-IP limiter irrelevant.
//
// A browser sets Origin itself and a page cannot forge it, so refusing a
// present-but-unlisted Origin closes the cross-site path. A missing Origin
// (curl, the health probe, a same-origin call) is still allowed through and
// stays covered by the rate limits and the budget.
export function isOriginAllowed(env: Env, request: Request): boolean {
  const origin = request.headers.get("Origin");
  if (!origin) return true;
  return allowlist(env).includes(origin) || LOCAL_ORIGIN_RE.test(origin);
}

export function jsonResponse(body: unknown, init: ResponseInit, env: Env, request: Request): Response {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Access-Control-Allow-Origin", pickAllowedOrigin(env, request));
  headers.set("Vary", "Origin");
  return new Response(JSON.stringify(body), { ...init, headers });
}

export function corsPreflight(env: Env, request: Request): Response {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": pickAllowedOrigin(env, request),
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    },
  });
}
