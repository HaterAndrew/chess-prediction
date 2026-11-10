import { describe, expect, it } from "vitest";
import { readCalibration, receiptValues } from "./store";
import { cohortHash, sha256, snapshotKey } from "./types";
import type { ReceiptCard, ReceiptSnapshot } from "./types";

async function data() {
  const id = await sha256("1");
  const card: ReceiptCard = { family: "Example Open", year: 2026, status: "live", current_count: 1,
    point_estimate: 2, regular_fee: 10, count_observed_at: "2026-11-09T01:00:00Z", count_cohort_hash: await cohortHash([id]) };
  const snapshot: ReceiptSnapshot = { schema: 1, family: card.family, year: 2026, tournament_id: "123",
    source_as_of: "2026-11-09T02:00:00Z", event_start: "2026-11-14", registration_close: "2026-11-15",
    regular_fee_cents: 1000, registration_count: 1, cohort: [{ id, paid_at: "2026-11-08T12:00:00Z" }],
    summary: { entry_cents: 1000, membership_cents: 0, contribution_cents: 0, other_cents: 0, refunded_cents: 0, net_cents: 1000 },
    buckets: [{ days_before: 2, registrations: 1, entry_cents: 1000, membership_cents: 0, contribution_cents: 0, other_cents: 0 }],
    previous_net_cents: null, previous_as_of: null };
  const history = { ...snapshot, year: 2025, registration_close: "2025-11-15" };
  const map = new Map([[snapshotKey(card.family, 2026), JSON.stringify(snapshot)],
    [`history:${encodeURIComponent(card.family)}`, JSON.stringify([history])]]);
  const kv = { get: async (key: string) => map.get(key) ?? null } as unknown as KVNamespace;
  return { card, snapshot, history, map, kv };
}

describe("financial fault containment", () => {
  it("retires a cached money projection when the attendance forecast is unavailable", async () => {
    const { card, snapshot, map, kv } = await data();
    const [projection] = await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z"));
    map.set(snapshotKey(card.family, 2026), JSON.stringify({ ...snapshot, projection }));
    expect((await receiptValues(kv, [{ ...card, point_estimate: 0 }], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toMatchObject({ value: 10, future_cents: 0, actual_cents: 1000, missing: null });
    for (const failed of [false, true]) {
      if (failed) {
        map.set("session:status", JSON.stringify({ attempted_at: "2026-11-09T03:30:00.000Z", ok: false, reason: "source_login_expired" }));
        map.set("history:pooled", "invalid JSON");
        map.set(`history:${encodeURIComponent(card.family)}`, "invalid JSON");
      }
      expect((await receiptValues(kv, [{ ...card, point_estimate: null }], Date.parse("2026-11-09T04:00:00Z")))[0])
        .toMatchObject({ value: null, future_cents: null, refund_reserve_cents: null, actual_cents: 1000, missing: "no_forecast" });
    }
  });
  it("refuses malformed session-health records instead of treating them as healthy", async () => {
    const { card, map, kv } = await data();
    for (const raw of ["invalid JSON", "null", "[]", JSON.stringify({ ok: "false", attempted_at: "2026-11-09T03:00:00.000Z", reason: null }),
      JSON.stringify({ ok: false, attempted_at: "invalid date", reason: "source_login_expired" }),
      JSON.stringify({ ok: true, attempted_at: "2026-11-09T03:00:00.000Z", reason: "unexpected" })]) {
      map.set("session:status", raw);
      await expect(receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z"))).rejects.toThrow();
    }
  });

  it("does not apply a session failure older than the financial snapshot", async () => {
    const { card, map, kv } = await data();
    map.set("session:status", JSON.stringify({ attempted_at: "2026-11-09T01:30:00.000Z", ok: false, reason: "source_login_expired" }));
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toMatchObject({ value: 20, stale: false, missing: null });
  });

  it("does not clear an existing collection failure after a healthy heartbeat", async () => {
    const { card, map, kv } = await data();
    map.set("collector:status", JSON.stringify({ attempted_at: "2026-11-09T03:00:00.000Z", ok: false, reason: "source_network_failed" }));
    map.set("session:status", JSON.stringify({ attempted_at: "2026-11-09T03:30:00.000Z", ok: true, reason: null }));
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toMatchObject({ value: null, stale: true, missing: "collection_failed" });
  });
  it("retains the prior amount and source date after a newer session failure", async () => {
    const { card, snapshot, map, kv } = await data();
    const [projection] = await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z"));
    map.set(snapshotKey(card.family, 2026), JSON.stringify({ ...snapshot, projection }));
    map.set("session:status", JSON.stringify({ attempted_at: "2026-11-09T03:30:00.000Z", ok: false, reason: "source_login_expired" }));
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toEqual({ ...projection, stale: true, missing: "collection_failed" });
  });

  it("does not let a successful heartbeat refresh the financial source date", async () => {
    const { card, map, kv } = await data();
    map.set("session:status", JSON.stringify({ attempted_at: "2026-11-09T03:30:00.000Z", ok: true, reason: null }));
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toMatchObject({ value: 20, source_as_of: "2026-11-09T02:00:00Z", stale: false, missing: null });
  });
  it("rejects a corrupt retained projection instead of displaying its amount", async () => {
    const { card, snapshot, map, kv } = await data();
    const [projection] = await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z"));
    map.set(snapshotKey(card.family, 2026), JSON.stringify({ ...snapshot, projection: { ...projection, value: 99999 } }));
    map.set("history:pooled", "invalid JSON");
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toMatchObject({ value: null, stale: true, missing: "invalid_receipts" });
  });
  it("uses valid family calibration when the pooled cache is corrupt", async () => {
    const { card, map, kv } = await data();
    map.set("history:pooled", "invalid JSON");
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z")))[0])
      .toMatchObject({ value: 20, confidence: "family", missing: null });
  });
  it("preserves the prior projection and timestamps when both calibration caches fail", async () => {
    const { card, snapshot, map, kv } = await data();
    const [projection] = await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z"));
    map.set(snapshotKey(card.family, 2026), JSON.stringify({ ...snapshot, projection }));
    map.set("history:pooled", "invalid JSON");
    map.set(`history:${encodeURIComponent(card.family)}`, "invalid JSON");
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T04:00:00Z")))[0])
      .toEqual({ ...projection, stale: true, missing: "calibration_unavailable" });
  });
  it("keeps good events available when another event's snapshot is corrupt", async () => {
    const { card, map, kv } = await data();
    map.set(snapshotKey("Broken Open", 2026), "invalid JSON");
    const values = await receiptValues(kv, [card, { ...card, family: "Broken Open" }], Date.parse("2026-11-09T03:00:00Z"));
    expect(values[0].value).toBe(20);
    expect(values[1]).toMatchObject({ value: null, missing: "invalid_receipts" });
  });
  it("supplies pooled calibration even when a family record is unusable", async () => {
    const { card, snapshot, history, map, kv } = await data();
    map.set(`history:${encodeURIComponent(card.family)}`, JSON.stringify([{ ...history, regular_fee_cents: null }]));
    map.set("history:pooled", JSON.stringify([{ ...history, family: "Another Open" }]));
    expect((await readCalibration(kv, card.family)).length).toBe(2);
    const values = await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z"));
    expect(values[0]).toMatchObject({ value: 20, confidence: "pooled" });
    const projection = { ...values[0], value: 19, future_cents: 900 };
    map.set(snapshotKey(card.family, 2026), JSON.stringify({ ...snapshot, projection }));
    map.set("collector:status", JSON.stringify({ attempted_at: "2026-11-09T02:30:00.000Z", ok: false, reason: "source_login_expired" }));
    expect((await receiptValues(kv, [card], Date.parse("2026-11-09T03:00:00Z")))[0])
      .toMatchObject({ value: 19, stale: true, missing: "collection_failed" });
  });
});
