// Rate limit, daily budget, and model pricing (index.ts, verbatim; W1).
import type Anthropic from "@anthropic-ai/sdk";

import type { Env } from "./env";

// I2 (rate limit only): the per-IP and global rate counters still use KV
// read-then-write, which is not atomic — N concurrent requests can each read the
// same count and all write count+1, letting a burst slip past the per-minute cap.
// That overshoot is bounded by a minute and backstopped by the daily budget,
// which since the 2026-09-07 review no longer shares the flaw (see below). The
// atomic fix for these two remains a Durable Object; it is deliberately not
// shipped unverified, because a broken DO migration takes the live worker down
// on deploy and cannot be exercised without `wrangler dev` + a deployed DO.
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
  return bumpCounter(env, `rl:${ip}:${minuteBucket()}`, limit);
}

// A per-IP limit alone throttles nothing: `cf-connecting-ip` cannot be spoofed,
// but a residential IPv6 /64 hands an attacker 2^64 distinct buckets for free,
// and a cross-site POST spreads the load over every visitor's own address. This
// ceiling is the one an attacker cannot rotate around. Sized well above what the
// site's own traffic produces, so it only binds under abuse.
const DEFAULT_GLOBAL_RATE_LIMIT_PER_MIN = 60;

export async function checkGlobalRateLimit(env: Env): Promise<{ ok: boolean; retryAfter?: number }> {
  if (!env.KV) {
    console.error('KV binding unavailable — refusing request (global rate limit cannot be enforced)');
    return { ok: false, retryAfter: 30 };
  }
  const parsed = parseInt(env.GLOBAL_RATE_LIMIT_PER_MIN ?? '', 10);
  const limit = Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_GLOBAL_RATE_LIMIT_PER_MIN;
  return bumpCounter(env, `rl:global:${minuteBucket()}`, limit);
}

function minuteBucket(): number {
  return Math.floor(Date.now() / 60_000);
}

function retryAfterSeconds(): number {
  return 60 - Math.floor((Date.now() % 60_000) / 1000);
}

async function bumpCounter(env: Env, key: string, limit: number): Promise<{ ok: boolean; retryAfter?: number }> {
  const raw = await env.KV!.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= limit) return { ok: false, retryAfter: retryAfterSeconds() };
  await env.KV!.put(key, String(count + 1), { expirationTtl: 120 });
  return { ok: true };
}

// Aligned with wrangler.toml DAILY_BUDGET_USD. Used only when the var is unset
// or non-numeric; a configured "0" now correctly disables spend (was impossible
// with `|| 2`, which also silently doubled a blank cap). (I4)
const DEFAULT_DAILY_BUDGET_USD = 1;

// The spend counter is sharded, one immutable KV key per recorded charge, and
// the total is a list+sum rather than a read-modify-write.
//
// 2026-09-07 review: the old single-key `get` -> `+delta` -> `put` was
// last-writer-wins, so N concurrent turns each read the same base and
// overwrote each other, recording roughly ONE delta instead of N. It
// undercounted systematically rather than overshooting by a bounded amount.
// The `get` also passed no cacheTtl, so each Cloudflare PoP served a value up
// to 60s stale and the cap was effectively per-PoP, per-minute. Worst case per
// request is MAX_TURNS x max_tokens at Sonnet output rates (~$0.48) against a
// $1.00 cap, so a burst of concurrent POSTs billed roughly $96 while the
// counter recorded one charge.
//
// Writes to distinct keys cannot lose updates, so the sum is exact for
// everything KV has converged on. The residual is list read-after-write lag,
// which can hide a charge written moments ago; `extraUsd` closes that for the
// in-flight request, which is where the concurrency actually lives.
const COST_KEY_TTL_SECONDS = 86400 * 2;
// One page is 1000 charges for a single day. Reaching a second page means spend
// is orders of magnitude past any sane cap, so stop counting and refuse.
const MAX_COST_PAGES = 2;

function costPrefix(day: string): string {
  return `cost:${day}:`;
}

function utcDay(): string {
  return new Date().toISOString().slice(0, 10);
}

async function sumDailySpend(env: Env, day: string): Promise<number> {
  let total = 0;
  let cursor: string | undefined;
  for (let page = 0; page < MAX_COST_PAGES; page++) {
    const res = await env.KV!.list<{ usd?: number }>({ prefix: costPrefix(day), cursor });
    for (const k of res.keys) {
      const usd = k.metadata?.usd;
      if (typeof usd === 'number' && Number.isFinite(usd)) total += usd;
    }
    if (res.list_complete) return total;
    cursor = res.cursor;
  }
  // More charges than MAX_COST_PAGES can hold. Refuse rather than report a
  // partial sum that would read as "under budget".
  console.error(`Daily spend ledger for ${day} exceeded ${MAX_COST_PAGES} pages — refusing request`);
  return Number.POSITIVE_INFINITY;
}

export async function checkDailyBudget(
  env: Env,
  extraUsd = 0,
): Promise<{ ok: boolean; spent: number; cap: number }> {
  const parsed = parseFloat(env.DAILY_BUDGET_USD);
  const cap = Number.isFinite(parsed) ? parsed : DEFAULT_DAILY_BUDGET_USD;
  // v3 S3: fail closed for the same reason as checkRateLimit. Without KV the
  // spend counter cannot be read OR written, so every request would look like
  // the first one of the day and the cap would never bind.
  if (!env.KV) {
    console.error('KV binding unavailable — refusing request (daily budget cannot be enforced)');
    return { ok: false, spent: 0, cap };
  }
  const committed = await sumDailySpend(env, utcDay());
  // extraUsd is what THIS request has already been charged. KV list is
  // eventually consistent, so a charge recorded a moment ago may not be listed
  // yet; counting it locally keeps the per-turn loop exact for the request that
  // is actually spending.
  const spent = committed + extraUsd;
  return { ok: spent < cap, spent, cap };
}

export async function recordCost(env: Env, usdDelta: number): Promise<void> {
  if (!env.KV) return;
  if (!Number.isFinite(usdDelta) || usdDelta <= 0) return;
  // A fresh key per charge: independent writes, no lost updates. The value is
  // empty because the amount rides in metadata, which list() returns inline —
  // one list call totals the day instead of one get per charge.
  const key = `${costPrefix(utcDay())}${crypto.randomUUID()}`;
  await env.KV.put(key, '', {
    metadata: { usd: usdDelta },
    expirationTtl: COST_KEY_TTL_SECONDS,
  });
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
