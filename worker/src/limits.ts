// Rate limit, daily budget, and model pricing (index.ts, verbatim; W1).
import type Anthropic from "@anthropic-ai/sdk";

import type { Env } from "./env";

// I2 (known limitation): the rate-limit and daily-budget counters use KV
// read-then-write, which is not atomic — N concurrent requests can each read the
// same count and all write count+1, letting a burst slip a little past the cap.
// For a personal app with a soft $1/day budget the overshoot is negligible. The
// atomic fix is a Durable Object (or the CF rate-limit binding): move the
// get/increment/put into a single-threaded DO method and call it here. Left as a
// documented follow-up rather than shipped unverified — a broken DO migration
// takes the live worker down on deploy, and it can't be exercised without
// `wrangler dev` + a deployed DO.
export async function checkRateLimit(env: Env, ip: string): Promise<{ ok: boolean; retryAfter?: number }> {
  // v3 S3: fail CLOSED when the KV binding is missing. This used to return
  // ok:true, so a KV outage, a renamed binding or a botched deploy silently
  // removed the rate limit and the daily budget at the same time — the two
  // controls that bound Anthropic spend — while the endpoint kept serving. An
  // unavailable limiter means the request cannot be shown to be within limits,
  // and for a paid upstream that has to read as "no".
  if (!env.KV) {
    console.error('KV binding unavailable — refusing request (rate limit cannot be enforced)');
    return { ok: false, retryAfter: 30 };
  }
  const limit = parseInt(env.RATE_LIMIT_PER_MIN, 10) || 20;
  const bucket = Math.floor(Date.now() / 60_000);
  const key = `rl:${ip}:${bucket}`;
  const raw = await env.KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= limit) return { ok: false, retryAfter: 60 - Math.floor((Date.now() % 60_000) / 1000) };
  await env.KV.put(key, String(count + 1), { expirationTtl: 120 });
  return { ok: true };
}

// Aligned with wrangler.toml DAILY_BUDGET_USD. Used only when the var is unset
// or non-numeric; a configured "0" now correctly disables spend (was impossible
// with `|| 2`, which also silently doubled a blank cap). (I4)
const DEFAULT_DAILY_BUDGET_USD = 1;

export async function checkDailyBudget(env: Env): Promise<{ ok: boolean; spent: number; cap: number }> {
  const parsed = parseFloat(env.DAILY_BUDGET_USD);
  const cap = Number.isFinite(parsed) ? parsed : DEFAULT_DAILY_BUDGET_USD;
  // v3 S3: fail closed for the same reason as checkRateLimit. Without KV the
  // spend counter cannot be read OR written, so every request would look like
  // the first one of the day and the cap would never bind.
  if (!env.KV) {
    console.error('KV binding unavailable — refusing request (daily budget cannot be enforced)');
    return { ok: false, spent: 0, cap };
  }
  const day = new Date().toISOString().slice(0, 10);
  const raw = await env.KV.get(`cost:${day}`);
  const spent = raw ? parseFloat(raw) : 0;
  return { ok: spent < cap, spent, cap };
}

export async function recordCost(env: Env, usdDelta: number): Promise<void> {
  if (!env.KV) return;
  const day = new Date().toISOString().slice(0, 10);
  const key = `cost:${day}`;
  const raw = await env.KV.get(key);
  const spent = raw ? parseFloat(raw) : 0;
  await env.KV.put(key, (spent + usdDelta).toFixed(4), { expirationTtl: 86400 * 2 });
}

// I1: per-model USD/MTok price table. Keyed by model-id prefix so dated
// variants (…-20250101) match. Budget accounting must fail loud on an unknown
// model rather than silently bill Sonnet rates for an Opus deployment.
interface ModelPricing {
  input: number;
  output: number;
  cacheWrite: number;
  cacheRead: number;
}
const MODEL_PRICING: Record<string, ModelPricing> = {
  // Sonnet 5 standard rate (intro $2/$10 runs through 2026-08-31; the budget
  // guard uses the durable rate so it over-counts, never under-counts).
  "claude-sonnet-5": { input: 3.0, output: 15.0, cacheWrite: 3.75, cacheRead: 0.3 },
  "claude-sonnet-4": { input: 3.0, output: 15.0, cacheWrite: 3.75, cacheRead: 0.3 },
  "claude-opus-4": { input: 15.0, output: 75.0, cacheWrite: 18.75, cacheRead: 1.5 },
  "claude-haiku-4": { input: 1.0, output: 5.0, cacheWrite: 1.25, cacheRead: 0.1 },
};
// code_execution bills container uptime separately (~$0.05/hour). We can't see
// wall-clock per request, so add a small per-invocation term when it ran.
const CODE_EXEC_COST_PER_CALL = 0.0005;

export function pricingFor(model: string): ModelPricing {
  const key = Object.keys(MODEL_PRICING).find(k => model.startsWith(k));
  if (!key) {
    throw new Error(`No price table entry for model "${model}" — add it to MODEL_PRICING before deploying.`);
  }
  return MODEL_PRICING[key];
}

export function estimateCost(usage: Anthropic.Beta.BetaUsage, model: string, codeExecCalls = 0): number {
  const p = pricingFor(model);
  const i = usage.input_tokens ?? 0;
  const o = usage.output_tokens ?? 0;
  const cw = usage.cache_creation_input_tokens ?? 0;
  const cr = usage.cache_read_input_tokens ?? 0;
  const tokenCost = ((i * p.input) + (o * p.output) + (cw * p.cacheWrite) + (cr * p.cacheRead)) / 1_000_000;
  return tokenCost + codeExecCalls * CODE_EXEC_COST_PER_CALL;
}
