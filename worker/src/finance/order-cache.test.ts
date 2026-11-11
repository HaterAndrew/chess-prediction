import { describe, expect, it } from "vitest";
import { OrderAcquisition } from "./order-cache";
import { sha256 } from "./types";

function source(extra: Record<string, unknown> = {}) {
  return { order_id: "1", tournament: "2026 Example Open", section: "Open", payment_date: "2026-11-01", payment_time: "12:00:00",
    payment_type: "2", is_deleted: false, status: "Approved", paypal_trans_id: "private-transaction-reference",
    section_amount: "12.00", membership_amount: "", order_value: "10.00", other_fees: "", paypal_credit_card_fee_contribution: "",
    public_discount_amount: "", discount_amount: "", player_email: "private-person@example.invalid", uscf_id: "12345678", ...extra };
}
function storage() {
  const data = new Map<string, string>();
  const writes: string[] = [];
  const kv = { get: async (key: string) => data.get(key) ?? null,
    put: async (key: string, value: string) => { writes.push(key); data.set(key, value); } } as unknown as KVNamespace;
  return { data, kv, writes };
}

describe("financial acquisition checkpoints", () => {
  it("retains exact yearless invoice labels without admitting a different event", async () => {
    const { kv } = storage();
    const selected = source({ tournament: "Saratoga Tournament Of-The-Ages Open", invoice_event_subtotal_cents: 1000 });
    const first = new OrderAcquisition(kv, "Saratoga Tournament Of-The-Ages Open|2027");
    await first.rows("invoice:2:1", [selected], async () => [selected]);
    await first.checkpoint();
    const resumed = new OrderAcquisition(kv, "Saratoga Tournament Of-The-Ages Open|2027");
    expect(await resumed.rows("invoice:2:1", [selected], async () => { throw Error("unexpected_source_read"); }))
      .toMatchObject([{ tournament: selected.tournament, invoice_event_subtotal_cents: 1000 }]);
    const wrong = { ...selected, tournament: "2026 Saratoga Tournament Of-The-Ages Open" };
    await expect(resumed.rows("invoice:2:1", [wrong], async () => [selected])).rejects.toThrow("shared_order_line_missing");
  });
  it("persists many verified orders with one bounded checkpoint write", async () => {
    const { kv, writes } = storage();
    const acquisition = new OrderAcquisition(kv, "Example Open|2026");
    for (let i = 1; i <= 40; i++) {
      const row = source({ order_id: String(i) });
      await acquisition.rows(`ref${i}`, [row], async () => [row]);
    }
    expect(writes).toHaveLength(0);
    await acquisition.checkpoint();
    expect(writes).toHaveLength(1);
  });
  it("does not count an unchanged pending prefix as progress when its tail cannot be acquired", async () => {
    const { kv } = storage(); const first = new OrderAcquisition(kv, "Example Open|2026");
    await first.rows("prefix", [source()], async () => [source()]); await first.checkpoint();
    const second = new OrderAcquisition(kv, "Example Open|2026");
    await second.rows("prefix", [source()], async () => { throw Error("unexpected_source_read"); });
    await expect(second.rows("tail", [source()], async () => { throw Error("source_request_limit"); })).rejects.toThrow("source_request_limit");
    await second.checkpoint(); expect(second.progressed).toBe(0);
  });
  it("cannot reopen a retired generation when a late partial writer overwrites the root", async () => {
    const { data, kv, writes } = storage(); let now = Date.parse("2026-11-09T02:00:00Z");
    const first = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await first.rows("ref", [source()], async () => [source()]); await first.checkpoint();
    const oldRoot = data.get(writes[0])!;
    const complete = new OrderAcquisition(kv, "Example Open|2026", () => now + 1000);
    await complete.rows("ref", [source()], async () => { throw Error("unexpected_source_read"); }); await complete.checkpoint(true);
    data.set(writes[0], oldRoot); // Simulate a delayed duplicate overwriting only mutable progress.
    now += 3 * 86_400_000; let loads = 0;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [source()], async () => { loads++; return [source()]; });
    expect(loads).toBe(1);
  });
  it("retires contradictory proof authority even when an older partial writer restores the root", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z");
    const seed = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await seed.rows("refA", [source()], async () => [source()]); await seed.checkpoint();
    const old = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await old.rows("refA", [source()], async () => { throw Error("unexpected_source_read"); });
    await old.rows("refB", [source()], async () => [source()]);
    const fresh = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await fresh.rows("refA", [source()], async () => { throw Error("unexpected_source_read"); });
    expect(fresh.refreshAfterContradiction()).toBe(true); await fresh.checkpoint(); await old.checkpoint();
    let calls = 0;
    const resumed = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await resumed.rows("refA", [source()], async () => { calls++; return [source()]; }); await resumed.checkpoint();
    expect(calls).toBe(1); // Even evidence younger than24h must be fetched afresh after contradiction.
    now += 3 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("refA", [source()], async () => { calls++; return [source()]; });
    expect(calls).toBe(1);
  });
  it("resumes repaired fresh proofs beyond 24 hours after a corrupt checkpoint", async () => {
    const { data, kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z");
    data.set("order_checkpoint:2:Example%20Open%7C2026", "invalid JSON");
    const first = new OrderAcquisition(kv, "Example Open|2026", () => now);
    let calls = 0;
    await first.rows("ref", [source()], async () => { calls++; return [source()]; }); await first.checkpoint();
    now += 3 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [source()], async () => { calls++; return [source()]; });
    expect(calls).toBe(1);
  });
  it("retains only normalized financial fields and resumes after freshness-cache expiry", async () => {
    const { data, kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const load = async () => { calls++; return [row]; };
    const first = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await first.rows("private-transaction-reference", [row], load); await first.checkpoint();
    const persisted = [...data.values()].join("\n");
    expect(persisted).not.toContain("private-person"); expect(persisted).not.toContain("12345678");
    expect(persisted).not.toContain("private-transaction-reference");
    now += 3 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("private-transaction-reference", [row], load);
    expect(calls).toBe(1);
  });
  it("invalidates an order when a selected-event line disappears", async () => {
    const { kv } = storage(); const now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const first = source(); const second = source({ section: "Under 1600" });
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [first, second], async () => [first, second]); await acquisition.checkpoint();
    await new OrderAcquisition(kv, "Example Open|2026", () => now + 1000).rows("ref", [first], async () => { calls++; return [first]; });
    expect(calls).toBe(1);
  });
  it("refreshes cross-event order evidence after 24 hours even while acquisition is pending", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const other = source({ tournament: "2026 Another Open" });
    const load = async () => { calls++; return [row, other]; };
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [row], load); await acquisition.checkpoint();
    now += 2 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [row], load);
    expect(calls).toBe(2);
  });
  it("persists a retirement fence before a complete report can be published", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const load = async () => { calls++; return [row]; };
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [row], load); now += 1000; await acquisition.checkpoint(true);
    now += 2 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [row], load);
    expect(calls).toBe(2);
  });
  it("also retires older progress using an independently published snapshot", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const load = async () => { calls++; return [row]; };
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [row], load); await acquisition.checkpoint();
    const publishedAt = new Date(now + 1000).toISOString();
    now += 3 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now, publishedAt).rows("ref", [row], load);
    expect(calls).toBe(2);
  });
  it("loads a packed checkpoint once and bounds temporary legacy migration reads", async () => {
    const data = new Map<string, string>(); let reads = 0;
    const kv = { get: async (key: string | string[]) => {
      reads++; return Array.isArray(key) ? new Map(key.map(k => [k, data.get(k) ?? null])) : data.get(key) ?? null;
    }, put: async (key: string, value: string) => { data.set(key, value); } } as unknown as KVNamespace;
    const acquisition = new OrderAcquisition(kv, "Example Open|2026");
    await acquisition.prefetch(Array.from({ length: 250 }, (_, i) => `ref${i}`));
    const prefixReads = reads;
    for (let i = 0; i < 64; i++) await acquisition.rows(`ref${i}`, [source()], async () => [source()]);
    await expect(acquisition.rows("next", [source()], async () => [source()])).rejects.toThrow("order_cache_read_limit");
    expect(prefixReads).toBe(1); expect(reads).toBe(129);
    await acquisition.checkpoint();
    const second = new OrderAcquisition(kv, "Example Open|2026");
    await second.prefetch(Array.from({ length: 64 }, (_, i) => `ref${i}`));
    const before = reads;
    for (let i = 0; i < 64; i++) await second.rows(`ref${i}`, [source()], async () => { throw Error("unexpected_source_read"); });
    expect(reads).toBe(before);
  });
  it("refuses an acquisition cache above its explicit memory envelope", async () => {
    let cancelled = false;
    const kv = { get: async (key: string) => key.startsWith("order_checkpoint:") ? null : new ReadableStream({
      start(controller) { controller.enqueue(new Uint8Array(4_000_000)); controller.enqueue(new Uint8Array(4_000_001)); },
      cancel() { cancelled = true; },
    }) } as unknown as KVNamespace;
    await expect(new OrderAcquisition(kv, "Example Open|2026").rows("first", [source()], async () => []))
      .rejects.toThrow("order_cache_capacity_exceeded");
    expect(cancelled).toBe(true);
  });
  it("imports fresh legacy proofs without changing their acquisition time or deleting old keys", async () => {
    const { data, kv, writes } = storage(); const now = Date.parse("2026-11-09T02:00:00Z");
    const observed = new Date(now - 1000).toISOString(); const hash = await sha256("ref");
    const oldKey = `order_progress:1:Example%20Open%7C2026:${hash}`;
    data.set(oldKey, JSON.stringify({ schema: 1, observed_at: observed, acquired_at: observed, rows: [source()] }));
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [source()], async () => { throw Error("unexpected_source_read"); });
    await acquisition.checkpoint();
    const packed = JSON.parse(data.get(writes[0])!);
    expect(packed.orders[hash]).toMatchObject({ acquired_at: observed, observed_at: observed, migrated: true });
    expect(data.has(oldKey)).toBe(true);
    let calls = 0;
    await new OrderAcquisition(kv, "Example Open|2026", () => now + 3 * 86_400_000).rows("ref", [source()], async () => { calls++; return [source()]; });
    expect(calls).toBe(1);
  });
  it("never reuses aged legacy progress with unknown retirement authority", async () => {
    const { data, kv } = storage(); const now = Date.parse("2026-11-09T02:00:00Z");
    const old = new Date(now - 3 * 86_400_000).toISOString(); const hash = await sha256("ref");
    data.set(`order_progress:1:Example%20Open%7C2026:${hash}`, JSON.stringify({ schema: 1, observed_at: old, acquired_at: old, rows: [source()] }));
    let calls = 0;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [source()], async () => { calls++; return [source()]; });
    expect(calls).toBe(1);
  });
  it("memoizes a failed checkpoint write and never pretends it was persisted", async () => {
    const { data, kv } = storage(); let puts = 0;
    kv.put = async () => { puts++; throw Error("storage_offline"); };
    const acquisition = new OrderAcquisition(kv, "Example Open|2026");
    await acquisition.rows("ref", [source()], async () => [source()]);
    await expect(acquisition.checkpoint()).rejects.toThrow("storage_offline");
    await expect(acquisition.checkpoint()).rejects.toThrow("storage_offline");
    expect(puts).toBe(1); expect(data.size).toBe(0);
  });
  it("keeps the previous checkpoint intact when a new proof exceeds the byte envelope", async () => {
    const { data, kv, writes } = storage();
    const first = new OrderAcquisition(kv, "Example Open|2026");
    await first.rows("ref", [source()], async () => [source()]); await first.checkpoint();
    const previous = data.get(writes[0]);
    const oversized = Array.from({ length: 9000 }, () => source({ order_id: "2", section: "棋".repeat(240) }));
    const second = new OrderAcquisition(kv, "Example Open|2026");
    await expect(second.rows("large", oversized, async () => oversized)).rejects.toThrow("order_cache_capacity_exceeded");
    await second.checkpoint();
    expect(data.get(writes[0])).toBe(previous); expect(writes).toHaveLength(1);
  });
  it("retires every included proof even when the clock moves backwards before publication", async () => {
    const { data, kv, writes } = storage(); let now = Date.parse("2026-11-09T02:00:00Z");
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [source()], async () => [source()]);
    now -= 1000; await acquisition.checkpoint(true);
    const checkpoint = JSON.parse(data.get(writes[0])!);
    expect(Object.values(checkpoint.orders).every((order: any) => Date.parse(order.acquired_at) <= Date.parse(checkpoint.retired_at))).toBe(true);
  });
  it("forces one resumable fresh generation after cached evidence contradicts source totals", async () => {
    const { data, kv, writes } = storage(); const now = Date.parse("2026-11-09T02:00:00Z");
    const first = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await first.rows("ref", [source()], async () => [source()]); await first.checkpoint();
    const second = new OrderAcquisition(kv, "Example Open|2026", () => now + 1000);
    await second.rows("ref", [source()], async () => { throw Error("unexpected_source_read"); });
    expect(second.refreshAfterContradiction()).toBe(true); await second.checkpoint();
    expect(JSON.parse(data.get(writes.at(-1)!)!).orders).toEqual({});
    let calls = 0;
    const third = new OrderAcquisition(kv, "Example Open|2026", () => now + 2000);
    await third.rows("ref", [source()], async () => { calls++; return [source()]; }); await third.checkpoint();
    const fourth = new OrderAcquisition(kv, "Example Open|2026", () => now + 3000);
    await fourth.rows("ref", [source()], async () => { throw Error("unexpected_source_read"); });
    expect(fourth.refreshAfterContradiction()).toBe(false); expect(calls).toBe(1);
  });
  it("rejects future-dated acquisition authority instead of extending stale proofs", async () => {
    const { data, kv } = storage(); const now = Date.parse("2026-11-09T02:00:00Z"); const hash = await sha256("ref");
    data.set("order_checkpoint:2:Example%20Open%7C2026", JSON.stringify({ schema: 2, scope: "Example Open|2026",
      generation: "11111111-1111-4111-8111-111111111111", retired_at: null, refresh_started_at: null,
      orders: { [hash]: { schema: 1, observed_at: new Date(now - 1000).toISOString(), acquired_at: new Date(now + 86_400_000).toISOString(), rows: [source()] } } }));
    let calls = 0;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [source()], async () => { calls++; return [source()]; });
    expect(calls).toBe(1);
  });
  it("requires exact invoice evidence for the new per-order checkpoint version", async () => {
    const { kv } = storage(); const row = source();
    await expect(new OrderAcquisition(kv, "Example Open|2026").rows("invoice:2:1", [row], async () => [row]))
      .rejects.toThrow("invoice_schema_changed");
  });
  it("propagates storage I/O failure instead of silently refetching", async () => {
    const kv = { get: async () => { throw new Error("storage_offline"); } } as unknown as KVNamespace;
    await expect(new OrderAcquisition(kv, "Example Open|2026").rows("ref", [source()], async () => []))
      .rejects.toThrow("storage_offline");
  });
});

it("retains only validated net-discount evidence across checkpoint reuse", async () => {
  const {kv}=storage();const row=source({section_amount:"10.00",order_value:"10.00"});
  const proof={...row,invoice_event_subtotal_cents:800,invoice_discount_variant:"single_approved_discount_net_v1",invoice_discount_cents:200,invoice_net_order_cents:800};
  const first=new OrderAcquisition(kv,"Example Open|2026");
  await first.rows("invoice:2:1",[row],async()=>[proof]);await first.checkpoint();
  const second=new OrderAcquisition(kv,"Example Open|2026");
  expect((await second.rows("invoice:2:1",[row],async()=>{throw Error("unexpected_source_read");}))[0]).toMatchObject({invoice_event_subtotal_cents:800,invoice_discount_variant:"single_approved_discount_net_v1",invoice_discount_cents:200,invoice_net_order_cents:800});
  for(const bad of [{invoice_discount_variant:"unknown"},{invoice_discount_cents:-1},{invoice_discount_cents:1001},{invoice_net_order_cents:900}]){
    await expect(new OrderAcquisition(storage().kv,"Example Open|2026").rows("invoice:2:1",[row],async()=>[{...proof,...bad}])).rejects.toThrow("invoice_schema_changed");
  }
});
