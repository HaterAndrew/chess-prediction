// CORS + JSON response helpers (index.ts, verbatim; W1).
import type { Env } from "./env";

export function pickAllowedOrigin(env: Env, request: Request): string {
  const allow = env.ALLOWED_ORIGIN.split(",").map((s) => s.trim()).filter(Boolean);
  const origin = request.headers.get("Origin");
  if (!origin) return allow[0] ?? "https://haterandrew.github.io";
  if (allow.includes(origin)) return origin;
  if (/^http:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$/i.test(origin)) return origin;
  return allow[0] ?? "https://haterandrew.github.io";
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
