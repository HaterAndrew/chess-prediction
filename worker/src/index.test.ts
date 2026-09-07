// Worker pure-logic tests (closes carried-forward X2's remaining gap).
// Pure-function coverage only: the KV-backed guards run against an in-memory
// fake, not miniflare. The spend ledger's concurrency behaviour IS asserted
// here (2026-09-07 review) because sharded keys make it testable without a
// real KV; the rate counters keep the I2 read-then-write race as a documented
// limitation, bounded by a minute and backstopped by the budget.
import { describe, expect, it } from "vitest";

// W1 split: import from the defining modules, not the routing entry.
import { timingSafeEqual } from "./cca-proxy";
import type { Env } from "./env";
import { isOriginAllowed, pickAllowedOrigin } from "./http";
import {
  checkDailyBudget,
  checkGlobalRateLimit,
  checkRateLimit,
  estimateCost,
  pricingFor,
  recordCost,
} from "./limits";

// Models the KV surface the limiter actually uses: get/put for the rate
// counters, and list-with-metadata for the sharded spend ledger. `list` returns
// keys in insertion order with their metadata attached, and honours prefix +
// cursor paging the way the real binding does.
function fakeKV(pageSize = 1000) {
  const store = new Map<string, string>();
  const meta = new Map<string, unknown>();
  return {
    store,
    meta,
    get: async (k: string) => store.get(k) ?? null,
    put: async (k: string, v: string, opts?: { metadata?: unknown }) => {
      store.set(k, v);
      if (opts?.metadata !== undefined) meta.set(k, opts.metadata);
    },
    list: async (opts?: { prefix?: string; cursor?: string }) => {
      const all = [...store.keys()].filter(k => !opts?.prefix || k.startsWith(opts.prefix));
      const start = opts?.cursor ? parseInt(opts.cursor, 10) : 0;
      const page = all.slice(start, start + pageSize);
      const end = start + page.length;
      return {
        keys: page.map(name => ({ name, metadata: meta.get(name) })),
        list_complete: end >= all.length,
        cursor: String(end),
      };
    },
  } as unknown as KVNamespace & {
    store: Map<string, string>;
    meta: Map<string, unknown>;
  };
}

function envWith(overrides: Partial<Env> = {}): Env {
  return {
    ANTHROPIC_API_KEY: "test",
    ALLOWED_ORIGIN: "https://haterandrew.github.io,http://localhost:8080",
    DATA_URL: "https://example.invalid/data.json",
    MODEL: "claude-sonnet-5",
    DAILY_BUDGET_USD: "1.00",
    RATE_LIMIT_PER_MIN: "20",
    KV: fakeKV(),
    ...overrides,
  } as Env;
}

// ── pricingFor ───────────────────────────────────────────────────────────────

describe("pricingFor", () => {
  it("throws loudly on an unknown model instead of billing a default", () => {
    expect(() => pricingFor("claude-fable-5")).toThrow(/No price table entry/);
  });

  it("matches the deployed model and dated variants by prefix", () => {
    expect(pricingFor("claude-sonnet-5").input).toBe(3.0);
    expect(pricingFor("claude-sonnet-5-20260901").output).toBe(15.0);
  });

  it("does not cross-match sonnet-5 onto the sonnet-4 entry", () => {
    // Both rates are equal today; assert key identity, not just values.
    expect(pricingFor("claude-sonnet-4-6")).not.toBe(pricingFor("claude-sonnet-5"));
    expect(pricingFor("claude-opus-4-1").input).toBe(15.0);
  });
});

// ── estimateCost ─────────────────────────────────────────────────────────────

describe("estimateCost", () => {
  const usage = {
    input_tokens: 1_000_000,
    output_tokens: 100_000,
    cache_creation_input_tokens: 200_000,
    cache_read_input_tokens: 400_000,
  } as never;

  it("sums all four token classes at the model's rates", () => {
    // 1M*3 + 0.1M*15 + 0.2M*3.75 + 0.4M*0.3 (per MTok) = 3 + 1.5 + 0.75 + 0.12
    expect(estimateCost(usage, "claude-sonnet-5")).toBeCloseTo(5.37, 6);
  });

  it("adds the per-invocation code-exec term", () => {
    const base = estimateCost(usage, "claude-sonnet-5");
    expect(estimateCost(usage, "claude-sonnet-5", 3)).toBeCloseTo(base + 0.0015, 6);
  });

  it("treats missing usage fields as zero", () => {
    expect(estimateCost({} as never, "claude-sonnet-5")).toBe(0);
  });
});

// ── pickAllowedOrigin ────────────────────────────────────────────────────────

describe("pickAllowedOrigin", () => {
  const env = envWith();
  const req = (origin?: string) =>
    new Request("https://worker.test/ask", {
      headers: origin ? { Origin: origin } : {},
    });

  it("echoes an allowlisted origin", () => {
    expect(pickAllowedOrigin(env, req("https://haterandrew.github.io"))).toBe(
      "https://haterandrew.github.io",
    );
  });

  it("falls back to the first allowlisted origin for a foreign one", () => {
    expect(pickAllowedOrigin(env, req("https://evil.example"))).toBe(
      "https://haterandrew.github.io",
    );
  });

  it("permits local dev hosts on any port", () => {
    expect(pickAllowedOrigin(env, req("http://127.0.0.1:5173"))).toBe("http://127.0.0.1:5173");
  });

  it("defaults when no Origin header is present", () => {
    expect(pickAllowedOrigin(env, req())).toBe("https://haterandrew.github.io");
  });
});

// ── rate limit + daily budget (fake KV) ─────────────────────────────────────

describe("checkRateLimit", () => {
  it("fails closed when the KV binding is missing", async () => {
    const res = await checkRateLimit(envWith({ KV: undefined as never }), "1.2.3.4");
    expect(res.ok).toBe(false);
  });

  it("admits up to the limit within a minute bucket, then refuses", async () => {
    const env = envWith({ RATE_LIMIT_PER_MIN: "3" });
    for (let i = 0; i < 3; i++) {
      expect((await checkRateLimit(env, "1.2.3.4")).ok).toBe(true);
    }
    const fourth = await checkRateLimit(env, "1.2.3.4");
    expect(fourth.ok).toBe(false);
    expect(fourth.retryAfter).toBeGreaterThan(0);
    expect(fourth.retryAfter).toBeLessThanOrEqual(60);
  });

  it("tracks IPs independently", async () => {
    const env = envWith({ RATE_LIMIT_PER_MIN: "1" });
    expect((await checkRateLimit(env, "1.1.1.1")).ok).toBe(true);
    expect((await checkRateLimit(env, "1.1.1.1")).ok).toBe(false);
    expect((await checkRateLimit(env, "2.2.2.2")).ok).toBe(true);
  });
});

describe("checkDailyBudget / recordCost", () => {
  it("fails closed without KV", async () => {
    const res = await checkDailyBudget(envWith({ KV: undefined as never }));
    expect(res.ok).toBe(false);
  });

  it("binds the cap after recorded spend crosses it", async () => {
    const env = envWith({ DAILY_BUDGET_USD: "0.10" });
    expect((await checkDailyBudget(env)).ok).toBe(true);
    await recordCost(env, 0.06);
    expect((await checkDailyBudget(env)).ok).toBe(true);
    await recordCost(env, 0.05);
    const after = await checkDailyBudget(env);
    expect(after.ok).toBe(false);
    expect(after.spent).toBeCloseTo(0.11, 4);
  });

  it("a configured 0 disables spend entirely (I4)", async () => {
    const env = envWith({ DAILY_BUDGET_USD: "0" });
    expect((await checkDailyBudget(env)).ok).toBe(false);
  });

  it("a non-numeric cap falls back to the $1 default, not NaN", async () => {
    const env = envWith({ DAILY_BUDGET_USD: "" });
    const res = await checkDailyBudget(env);
    expect(res.cap).toBe(1);
    expect(res.ok).toBe(true);
  });

  // 2026-09-07 review: the single-key read-modify-write recorded roughly ONE
  // charge no matter how many landed concurrently, so a burst billed far past
  // the cap while the counter barely moved. Each charge now gets its own key.
  it("records every concurrent charge instead of losing all but one", async () => {
    const env = envWith({ DAILY_BUDGET_USD: "100" });
    const n = 200;
    await Promise.all(Array.from({ length: n }, () => recordCost(env, 0.05)));
    const res = await checkDailyBudget(env);
    expect(res.spent).toBeCloseTo(n * 0.05, 4);
  });

  it("a concurrent burst cannot slip past the cap", async () => {
    const env = envWith({ DAILY_BUDGET_USD: "1.00" });
    await Promise.all(Array.from({ length: 200 }, () => recordCost(env, 0.48)));
    const res = await checkDailyBudget(env);
    expect(res.ok).toBe(false);
    expect(res.spent).toBeGreaterThan(90);
  });

  it("counts the in-flight request's own charges before the ledger converges", async () => {
    // extraUsd covers list read-after-write lag for the request doing the
    // spending, which is where the per-turn stop has to be exact.
    const env = envWith({ DAILY_BUDGET_USD: "0.10" });
    expect((await checkDailyBudget(env, 0.04)).ok).toBe(true);
    const res = await checkDailyBudget(env, 0.11);
    expect(res.ok).toBe(false);
    expect(res.spent).toBeCloseTo(0.11, 4);
  });

  it("ignores non-finite and non-positive deltas rather than poisoning the sum", async () => {
    const env = envWith({ DAILY_BUDGET_USD: "1.00" });
    await recordCost(env, NaN);
    await recordCost(env, -5);
    await recordCost(env, 0);
    await recordCost(env, 0.25);
    const res = await checkDailyBudget(env);
    expect(res.spent).toBeCloseTo(0.25, 4);
  });

  it("refuses rather than reporting a partial sum when the ledger overflows paging", async () => {
    // MAX_COST_PAGES is 2; a 1-key page forces a third.
    const env = envWith({ DAILY_BUDGET_USD: "1000", KV: fakeKV(1) });
    await recordCost(env, 0.01);
    await recordCost(env, 0.01);
    await recordCost(env, 0.01);
    const res = await checkDailyBudget(env);
    expect(res.ok).toBe(false);
    expect(res.spent).toBe(Number.POSITIVE_INFINITY);
  });
});

// ── global rate limit ────────────────────────────────────────────────────────

describe("checkGlobalRateLimit", () => {
  it("fails closed when the KV binding is missing", async () => {
    const res = await checkGlobalRateLimit(envWith({ KV: undefined as never }));
    expect(res.ok).toBe(false);
  });

  // The per-IP limit cannot bind an attacker rotating through an IPv6 /64 or
  // driving the endpoint from other people's browsers. This ceiling can.
  it("binds across callers regardless of source IP", async () => {
    const env = envWith({ GLOBAL_RATE_LIMIT_PER_MIN: "3" });
    expect((await checkGlobalRateLimit(env)).ok).toBe(true);
    expect((await checkGlobalRateLimit(env)).ok).toBe(true);
    expect((await checkGlobalRateLimit(env)).ok).toBe(true);
    const refused = await checkGlobalRateLimit(env);
    expect(refused.ok).toBe(false);
    expect(refused.retryAfter).toBeGreaterThan(0);
  });

  it("defaults to 60/min when unset or non-numeric", async () => {
    const env = envWith({ GLOBAL_RATE_LIMIT_PER_MIN: undefined });
    for (let i = 0; i < 60; i++) expect((await checkGlobalRateLimit(env)).ok).toBe(true);
    expect((await checkGlobalRateLimit(env)).ok).toBe(false);
  });

  it("is independent of the per-IP budget", async () => {
    const env = envWith({ GLOBAL_RATE_LIMIT_PER_MIN: "2", RATE_LIMIT_PER_MIN: "20" });
    await checkGlobalRateLimit(env);
    await checkGlobalRateLimit(env);
    expect((await checkGlobalRateLimit(env)).ok).toBe(false);
    // A fresh IP still passes its own per-IP check; the global gate is what stops it.
    expect((await checkRateLimit(env, "9.9.9.9")).ok).toBe(true);
  });
});

// ── origin authorization ─────────────────────────────────────────────────────

describe("isOriginAllowed", () => {
  const env = envWith();
  const withOrigin = (o?: string) =>
    new Request("https://w.example/ask", { headers: o ? { Origin: o } : {} });

  it("admits an allowlisted origin", () => {
    expect(isOriginAllowed(env, withOrigin("https://haterandrew.github.io"))).toBe(true);
  });

  // The cross-site POST path: a foreign page's Origin is set by the browser and
  // cannot be forged, so refusing it closes the CSRF vector on /ask.
  it("refuses a foreign origin", () => {
    expect(isOriginAllowed(env, withOrigin("https://evil.example"))).toBe(false);
  });

  it("still admits a request with no Origin (curl, health probe, same-origin)", () => {
    expect(isOriginAllowed(env, withOrigin(undefined))).toBe(true);
  });

  it("admits local dev hosts on any port", () => {
    expect(isOriginAllowed(env, withOrigin("http://localhost:5173"))).toBe(true);
  });

  it("does not confuse a lookalike host for localhost", () => {
    expect(isOriginAllowed(env, withOrigin("http://localhost.evil.example"))).toBe(false);
  });
});

// ── timingSafeEqual ──────────────────────────────────────────────────────────

describe("timingSafeEqual", () => {
  it("matches equal strings and rejects unequal ones", () => {
    expect(timingSafeEqual("secret", "secret")).toBe(true);
    expect(timingSafeEqual("secret", "secreT")).toBe(false);
    expect(timingSafeEqual("secret", "secret2")).toBe(false);
    expect(timingSafeEqual("", "")).toBe(true);
    expect(timingSafeEqual("", "x")).toBe(false);
  });
});
