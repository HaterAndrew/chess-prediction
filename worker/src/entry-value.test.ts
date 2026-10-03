// Entry-value figures (pure) and the /entry-value gate. KV is an in-memory
// fake and ASSETS a stub serving a fixed payload, as in index.test.ts.
import { describe, expect, it } from "vitest";

import type { Env } from "./env";
import { cleanSeries, entryValues, eventValue, type ValueCard } from "./entry-value";
import { FAIL_LIMIT_PER_IP, handleEntryValue, priceRedirect, VALUE_KEY_HEADER } from "./value-route";

const GENERATED = "2026-10-03";

// Day 0 is 2026-09-01; the series ends on day 32 = 2026-10-03.
function card(overrides: Partial<ValueCard> = {}): ValueCard {
  return {
    family: "Test Open",
    year: 2026,
    status: "live",
    current_count: 50,
    withdrawal_count: 0,
    daily_start_date: "2026-09-01",
    daily_data: [[0, 10], [10, 30], [31, 46], [32, 50]],
    early_bird_fee: null,
    early_bird_deadline: null,
    regular_fee: 100,
    onsite_fee: 120,
    ...overrides,
  };
}

describe("eventValue", () => {
  it("prices every paid entry at the regular fee without an early-bird tier", () => {
    const v = eventValue(card(), GENERATED);
    expect(v).toMatchObject({ value: 5000, basis: "regular", missing: null });
  });

  it("splits entries at the early-bird deadline", () => {
    // 30 entries by 2026-09-11 (day 10) at $80, the other 20 at $100.
    const v = eventValue(card({ early_bird_fee: 80, early_bird_deadline: "2026-09-11" }), GENERATED);
    expect(v).toMatchObject({ value: 30 * 80 + 20 * 100, basis: "early_bird" });
  });

  it("takes withdrawals out of the paid count", () => {
    expect(eventValue(card({ withdrawal_count: 5 }), GENERATED).value).toBe(4500);
  });

  it("falls back to the onsite fee and says so", () => {
    const v = eventValue(card({ regular_fee: null, onsite_fee: 50 }), GENERATED);
    expect(v).toMatchObject({ value: 2500, basis: "onsite" });
  });

  it("reports a missing fee instead of $0", () => {
    const v = eventValue(card({ regular_fee: null, onsite_fee: null }), GENERATED);
    expect(v).toMatchObject({ value: null, missing: "no_fee", last_day: null });
  });

  it("values the last day at the fee in effect that day", () => {
    expect(eventValue(card(), GENERATED).last_day).toEqual({ entries: 4, value: 400, span: 1 });
    const early = card({ early_bird_fee: 80, early_bird_deadline: "2026-10-03" });
    expect(eventValue(early, GENERATED).last_day).toEqual({ entries: 4, value: 320, span: 1 });
  });

  it("keeps a missed scrape's true span", () => {
    const gappy = card({ daily_data: [[0, 10], [29, 40], [32, 50]] });
    expect(eventValue(gappy, GENERATED).last_day).toEqual({ entries: 10, value: 1000, span: 3 });
  });

  it("has no last day when the series stopped before the generated date", () => {
    const stale = card({ daily_data: [[0, 10], [30, 49], [31, 50]] });
    expect(eventValue(stale, GENERATED).last_day).toBeNull();
  });
});

describe("cleanSeries", () => {
  it("sorts, dedupes, drops falls and points above the scraped count", () => {
    const pts = cleanSeries(card({ current_count: 40, daily_data: [[2, 30], [0, 10], [1, 25], [1, 20], [3, 28], [4, 90]] }));
    expect(pts).toEqual([[0, 10], [1, 25], [2, 30]]);
  });
});

describe("entryValues", () => {
  it("covers live events only", () => {
    const out = entryValues({ generated: GENERATED, tournaments: [card(), card({ status: "complete" })] });
    expect(out).toHaveLength(1);
  });
});

// ── the route ────────────────────────────────────────────────────────────────

function fakeKV() {
  const store = new Map<string, string>();
  return {
    store,
    get: async (k: string) => store.get(k) ?? null,
    put: async (k: string, v: string) => void store.set(k, v),
  } as unknown as KVNamespace & { store: Map<string, string> };
}

function assets(): Fetcher {
  return {
    fetch: async () => new Response(JSON.stringify({ generated: GENERATED, tournaments: [card()] })),
  } as unknown as Fetcher;
}

function envWith(overrides: Partial<Env> = {}): Env {
  return {
    ALLOWED_ORIGIN: "https://chessentries.com",
    ASSETS: assets(),
    KV: fakeKV(),
    ENTRY_VALUE_KEY: "correct horse",
    ...overrides,
  } as Env;
}

function get(key?: string, ip = "203.0.113.7"): Request {
  const headers: Record<string, string> = { "cf-connecting-ip": ip };
  if (key !== undefined) headers[VALUE_KEY_HEADER] = key;
  return new Request("https://chessentries.com/entry-value", { headers });
}

describe("handleEntryValue", () => {
  it("is closed when the secret is unset (every Preview)", async () => {
    const res = await handleEntryValue(envWith({ ENTRY_VALUE_KEY: undefined }), get("anything"));
    expect(res.status).toBe(403);
  });

  it("refuses when the limiter is unavailable", async () => {
    const res = await handleEntryValue(envWith({ KV: undefined }), get("correct horse"));
    expect(res.status).toBe(503);
  });

  it("rejects a missing or wrong key", async () => {
    const env = envWith();
    expect((await handleEntryValue(env, get())).status).toBe(401);
    expect((await handleEntryValue(env, get("wrong"))).status).toBe(401);
  });

  it("serves the figures, uncached, for the right key", async () => {
    const res = await handleEntryValue(envWith(), get("correct horse"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    const body = (await res.json()) as { generated: string; events: Array<{ value: number }> };
    expect(body.generated).toBe(GENERATED);
    expect(body.events[0].value).toBe(5000);
  });

  it("locks an address out after repeated wrong keys, even with the right one", async () => {
    const env = envWith();
    for (let i = 0; i < FAIL_LIMIT_PER_IP; i++) await handleEntryValue(env, get("wrong"));
    expect((await handleEntryValue(env, get("correct horse"))).status).toBe(429);
    expect((await handleEntryValue(env, get("correct horse", "198.51.100.9"))).status).toBe(200);
  });

  it("refuses other methods", async () => {
    const req = new Request("https://chessentries.com/entry-value", { method: "POST" });
    expect((await handleEntryValue(envWith(), req)).status).toBe(405);
  });
});

describe("priceRedirect", () => {
  it("sends /price to the page's unlock link on the same host, uncached", () => {
    const res = priceRedirect(new Request("https://chessentries.com/price"));
    expect(res.status).toBe(302);
    expect(res.headers.get("Location")).toBe("https://chessentries.com/#value");
    expect(res.headers.get("Cache-Control")).toBe("no-store");
  });
});
