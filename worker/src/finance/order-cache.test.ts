import { describe, expect, it } from "vitest";
import { OrderAcquisition } from "./order-cache";

function source(extra: Record<string, unknown> = {}) {
  return { order_id: "1", tournament: "2026 Example Open", section: "Open", payment_date: "2026-11-01", payment_time: "12:00:00",
    payment_type: "2", is_deleted: false, status: "Approved", paypal_trans_id: "private-transaction-reference",
    section_amount: "12.00", membership_amount: "", order_value: "10.00", other_fees: "", paypal_credit_card_fee_contribution: "",
    public_discount_amount: "", discount_amount: "", player_email: "private-person@example.invalid", uscf_id: "12345678", ...extra };
}
function storage() {
  const data = new Map<string, string>();
  const kv = { get: async (key: string) => data.get(key) ?? null,
    put: async (key: string, value: string) => { data.set(key, value); } } as unknown as KVNamespace;
  return { data, kv };
}

describe("financial acquisition checkpoints", () => {
  it("retains only normalized financial fields and resumes after freshness-cache expiry", async () => {
    const { data, kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const load = async () => { calls++; return [row]; };
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("private-transaction-reference", [row], load);
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
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [first, second], async () => [first, second]);
    await new OrderAcquisition(kv, "Example Open|2026", () => now + 1000).rows("ref", [first], async () => { calls++; return [first]; });
    expect(calls).toBe(1);
  });
  it("refreshes cross-event order evidence after 24 hours even while acquisition is pending", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const other = source({ tournament: "2026 Another Open" });
    const load = async () => { calls++; return [row, other]; };
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [row], load);
    now += 2 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [row], load);
    expect(calls).toBe(2);
  });
  it("retires durable progress only after a committed snapshot", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const load = async () => { calls++; return [row]; };
    const acquisition = new OrderAcquisition(kv, "Example Open|2026", () => now);
    await acquisition.rows("ref", [row], load); now += 1000; await acquisition.committed();
    now += 2 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [row], load);
    expect(calls).toBe(2);
  });
  it("retires progress using the published snapshot when the done-marker write failed", async () => {
    const { kv } = storage(); let now = Date.parse("2026-11-09T02:00:00Z"); let calls = 0;
    const row = source(); const load = async () => { calls++; return [row]; };
    await new OrderAcquisition(kv, "Example Open|2026", () => now).rows("ref", [row], load);
    const publishedAt = new Date(now + 1000).toISOString();
    now += 3 * 86_400_000;
    await new OrderAcquisition(kv, "Example Open|2026", () => now, publishedAt).rows("ref", [row], load);
    expect(calls).toBe(2);
  });
  it("prefetches checkpoints in bounded bulk reads instead of replaying individual gets", async () => {
    const data = new Map<string, string>(); let reads = 0;
    const kv = { get: async (key: string | string[]) => {
      reads++; return Array.isArray(key) ? new Map(key.map(k => [k, data.get(k) ?? null])) : data.get(key) ?? null;
    }, put: async (key: string, value: string) => { data.set(key, value); } } as unknown as KVNamespace;
    const acquisition = new OrderAcquisition(kv, "Example Open|2026");
    await acquisition.prefetch(Array.from({ length: 250 }, (_, i) => `ref${i}`));
    const prefixReads = reads;
    for (let i = 0; i < 250; i++) await acquisition.rows(`ref${i}`, [source()], async () => [source()]);
    expect(prefixReads).toBe(5); expect(reads).toBe(6);
  });
  it("refuses an acquisition cache above its explicit memory envelope", async () => {
    const kv = { get: async () => new Map([["unused", null]]) } as unknown as KVNamespace;
    kv.get = (async (keys: string[]) => new Map(keys.map(key => [key, "x".repeat(4_000_001)]))) as typeof kv.get;
    await expect(new OrderAcquisition(kv, "Example Open|2026").prefetch(["first", "second"]))
      .rejects.toThrow("order_cache_capacity_exceeded");
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
