import { describe, expect, it } from "vitest";
import { allocateCents } from "./allocation";
import { receiptForecast } from "./forecast";
import { cents, cohortHash, sha256, validateSnapshot } from "./types";
import type { ReceiptCard, ReceiptSnapshot } from "./types";

const NOW = Date.parse("2026-11-09T03:00:00Z");
async function example() {
  const cohort = await Promise.all([1, 2, 3, 4, 5].map(async n => ({ id: await sha256(String(n)), paid_at: "2026-11-08T12:00:00Z" })));
  const card: ReceiptCard = {
    family: "Example Open", year: 2026, status: "live", regular_fee: 10,
    current_count: 5, point_estimate: 10, count_observed_at: "2026-11-09T01:15:00Z",
    count_cohort_hash: await cohortHash(cohort.map(r => r.id)),
  };
  const snapshot: ReceiptSnapshot = {
    schema: 1, family: card.family, year: 2026, tournament_id: "123", event_start: "2026-11-14",
    registration_close: "2026-11-14", source_as_of: "2026-11-09T02:30:00Z", regular_fee_cents: 1000,
    registration_count: 5,
    summary: { entry_cents: 5000, membership_cents: 0, contribution_cents: 0, other_cents: 0, refunded_cents: 500, net_cents: 4500 },
    cohort, buckets: [], previous_net_cents: null, previous_as_of: null,
  };
  const history: ReceiptSnapshot = {
    ...snapshot, year: 2025, source_as_of: "2026-11-09T02:30:00Z", registration_close: "2025-11-15", registration_count: 10,
    summary: { ...snapshot.summary, entry_cents: 10000, refunded_cents: 1000, net_cents: 9000 },
    buckets: [{ days_before: 2, registrations: 10, entry_cents: 10000, membership_cents: 0, contribution_cents: 0, other_cents: 0 }],
  };
  return { card, snapshot, history };
}

describe("final recorded receipts", () => {
  it("adds future receipts and only the remaining cash refund reserve", async () => {
    const { card, snapshot, history } = await example();
    expect(await receiptForecast(card, snapshot, [history], NOW)).toMatchObject({
      value: 90, actual_cents: 4500, future_cents: 5000, refund_reserve_cents: 500, missing: null,
    });
  });
  it("recognizes payments after the model observation as already received", async () => {
    const { card, snapshot, history } = await example();
    snapshot.cohort.push({ id: await sha256("6"), paid_at: "2026-11-09T02:00:00Z" });
    snapshot.registration_count++;
    snapshot.summary.entry_cents += 1000;
    snapshot.summary.net_cents += 1000;
    const result = await receiptForecast(card, snapshot, [history], NOW);
    expect(result.future_cents).toBe(4000);
    expect(result.value).toBe(90);
  });
  it("refuses an equally sized but different registration cohort", async () => {
    const { card, snapshot, history } = await example();
    snapshot.cohort[0].id = await sha256("unrelated");
    expect(await receiptForecast(card, snapshot, [history], NOW)).toMatchObject({ value: null, missing: "unmatched_count" });
  });
  it("does not fall back to advertised fees for absent receipts or history", async () => {
    const { card, snapshot } = await example();
    expect((await receiptForecast(card, null, [], NOW)).missing).toBe("no_receipts");
    expect((await receiptForecast(card, snapshot, [], NOW)).missing).toBe("no_history");
  });
  it("rejects stale data, unknown observation times and future training editions", async () => {
    const { card, snapshot, history } = await example();
    expect((await receiptForecast(card, snapshot, [history], NOW + 48 * 3600000)).missing).toBe("stale_source");
    expect((await receiptForecast({ ...card, count_observed_at: null }, snapshot, [history], NOW)).missing).toBe("unmatched_count");
    expect((await receiptForecast(card, snapshot, [{ ...history, year: 2026 }], NOW)).missing).toBe("no_history");
  });
  it("keeps free entries in yield, includes memberships, and ignores walk-in totals", async () => {
    const { card, snapshot, history } = await example();
    history.buckets[0].registrations = 20;
    history.buckets[0].membership_cents = 2000;
    history.summary.membership_cents = 2000;
    history.summary.net_cents += 2000;
    const result = await receiptForecast({ ...card, total_estimate: 1000 } as ReceiptCard, snapshot, [history], NOW);
    expect(result.future_cents).toBe(3000);
  });
  it("prices late arrivals from historical late receipts rather than early receipts", async () => {
    const { card, snapshot, history } = await example();
    history.buckets.push({ ...history.buckets[0], days_before: 90, entry_cents: 1 });
    expect((await receiptForecast(card, snapshot, [history], NOW)).future_cents).toBe(5000);
  });
  it("reports negative recorded collection changes without implying entry growth", async () => {
    const { card, snapshot, history } = await example();
    snapshot.previous_as_of = "2026-11-08T02:30:00Z";
    snapshot.previous_net_cents = 5000;
    expect((await receiptForecast(card, snapshot, [history], NOW)).last_day).toEqual({ value: -5, span: 1 });
  });
});

describe("monetary contracts", () => {
  it("parses cents exactly and refuses blanks, markup, negative and oversized amounts", () => {
    expect(cents("$1,203.05")).toBe(120305);
    for (const v of ["", "1.005", "-1", "<b>1</b>", "99999999999999999", null]) expect(() => cents(v)).toThrow();
  });
  it("conserves contributions and partial refunds using original cash weights", () => {
    const weights = [{ id: "a", cash: 1000 }, { id: "b", cash: 2000 }, { id: "credit", cash: 0 }];
    expect(Object.fromEntries(allocateCents(101, weights))).toEqual({ a: 34, b: 67, credit: 0 });
    expect([...allocateCents(50, weights).values()].reduce((a, b) => a + b)).toBe(50);
    expect(() => allocateCents(1, [{ id: "credit", cash: 0 }])).toThrow("unattributed_receipt");
  });
  it("rejects inconsistent private snapshots instead of publishing partial actuals", async () => {
    const { snapshot } = await example();
    expect(validateSnapshot(snapshot)).toBe(snapshot);
    snapshot.summary.net_cents++;
    expect(() => validateSnapshot(snapshot)).toThrow("summary_mismatch");
  });
});
