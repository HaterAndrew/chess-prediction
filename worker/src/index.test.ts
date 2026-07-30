// Worker pure-logic tests (closes carried-forward X2's remaining gap).
// Pure-function coverage only: the KV-backed guards run against an in-memory
// fake, not miniflare — the I2 read-then-write race stays a documented
// limitation, not something these tests assert around.
import { describe, expect, it } from "vitest";

// W1 split: import from the defining modules, not the routing entry.
import { timingSafeEqual } from "./cca-proxy";
import type { Env } from "./env";
import { pickAllowedOrigin } from "./http";
import {
  checkDailyBudget,
  checkRateLimit,
  estimateCost,
  pricingFor,
  recordCost,
} from "./limits";

function fakeKV() {
  const store = new Map<string, string>();
  return {
    store,
    get: async (k: string) => store.get(k) ?? null,
    put: async (k: string, v: string, _opts?: unknown) => {
      store.set(k, v);
    },
  } as unknown as KVNamespace & { store: Map<string, string> };
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
