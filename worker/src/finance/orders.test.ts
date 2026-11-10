import { beforeEach, expect, it, vi } from "vitest";
import { buildReceiptSnapshot } from "./report";
import { acquireCartRows, invoiceCacheKey } from "./orders";
import { OrderAcquisition } from "./order-cache";
import type { ChessActionClient } from "./client";
import { invoiceContainsWholeOrder } from "./invoice";
vi.mock("./invoice", () => ({ invoiceContainsWholeOrder: vi.fn(async () => true) }));
const prove = async (_html: string, rows: Record<string, unknown>[], totals?: Map<string, number>) => {
  const events = [...new Set(rows.map(r => String(r.tournament)))];
  events.forEach(event => totals?.set(event, 1000 / events.length));
  return true;
};
beforeEach(() => { vi.mocked(invoiceContainsWholeOrder).mockReset().mockImplementation(prove); });
const row = (id: string, extra: Record<string, unknown> = {}) => ({ order_id: id, tournament: "2026 Example Open", section: "Open", payment_date: "2026-11-01", payment_time: "12:00:00", payment_type: "0", is_deleted: false, status: "Manual", paypal_trans_id: "Cash", section_amount: "10.00", membership_amount: "", order_value: "10.00", ...extra });
function storage() {
  const data = new Map<string, string>();
  return { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, data.get(k) ?? null])) : data.get(key) ?? null,
    put: async (key: string, value: string) => { data.set(key, value); } } as unknown as KVNamespace;
}
it("resumes a repeated Cash label at the next independently verified order", async () => {
  const kv = storage(); const expected = [row("1"), row("2"), row("3")];
  let calls = 0;
  const client = { invoice: async () => { if (++calls > 2) throw new Error("source_request_limit"); return "invoice"; }, playerRows: vi.fn() } as unknown as ChessActionClient;
  const first = new OrderAcquisition(kv, "Example Open|2026");
  await first.prefetch(expected.map(invoiceCacheKey));
  await expect(acquireCartRows(client, first, "Cash", expected)).rejects.toThrow("source_request_limit");
  expect(first.progressed).toBe(2);
  await first.checkpoint();
  calls = 0;
  const second = new OrderAcquisition(kv, "Example Open|2026");
  await second.prefetch(expected.map(invoiceCacheKey));
  expect(await acquireCartRows(client, second, "Cash", expected)).toHaveLength(3);
  expect(calls).toBe(1); expect(client.playerRows).not.toHaveBeenCalled();
});
it("loads every outside line when an invoice proves a cross-event cart", async () => {
  vi.mocked(invoiceContainsWholeOrder).mockResolvedValueOnce(false).mockImplementationOnce(prove);
  const own = row("1", { status: "Approved", paypal_trans_id: "unique", payment_type: "2" });
  const other = { ...own, tournament: "2026 Another Open" };
  const client = { invoice: async () => "invoice", playerRows: vi.fn(async () => [own, other]) } as unknown as ChessActionClient;
  expect(await acquireCartRows(client, new OrderAcquisition(storage(), "Example Open|2026"), "unique", [own])).toHaveLength(2);
  expect(client.playerRows).toHaveBeenCalledWith("All", "unique", ["1"]);
});
it("refuses an unverified cross-event cash cart without a broad Cash query", async () => {
  vi.mocked(invoiceContainsWholeOrder).mockResolvedValue(false);
  const client = { invoice: async () => "invoice", playerRows: vi.fn() } as unknown as ChessActionClient;
  await expect(acquireCartRows(client, new OrderAcquisition(storage(), "Example Open|2026"), "Cash", [row("1")])).rejects.toThrow("shared_order_details_required");
  expect(client.playerRows).not.toHaveBeenCalled();
});
it("rejects fallback rows that still contradict the invoice membership", async () => {
  vi.mocked(invoiceContainsWholeOrder).mockResolvedValue(false);
  const own = row("1", { status: "Approved", paypal_trans_id: "unique", payment_type: "2" });
  const client = { invoice: async () => "invoice", playerRows: vi.fn(async () => [own]) } as unknown as ChessActionClient;
  await expect(acquireCartRows(client, new OrderAcquisition(storage(), "Example Open|2026"), "unique", [own])).rejects.toThrow("shared_order_line_missing");
});

it("refuses unknown or refunded full-order Free rows through the real acquisition and report chain", async () => {
  for (const refund of ["Refunded", null, undefined, 0, " "]) {
    const own = row("1", { paypal_trans_id: "Free", is_refunded: "" });
    const refunded = { ...own, is_refunded: refund };
    vi.mocked(invoiceContainsWholeOrder).mockReset().mockResolvedValueOnce(false).mockImplementationOnce(prove);
    const client = { invoice: async () => "invoice", playerRows: vi.fn(async () => [refunded]) } as unknown as ChessActionClient;
    const acquisition = new OrderAcquisition(storage(), "Example Open|2026");
    await expect(buildReceiptSnapshot({family:"Example Open",year:2026,status:"live",current_count:1,event_start:"2026-11-14"}, "123", [own],
      {entry_cents:1000,membership_cents:0,contribution_cents:0,other_cents:0,refunded_cents:0,net_cents:1000}, "2026-11-09T02:30:00Z",
      (transaction,expected)=>acquireCartRows(client,acquisition,transaction,expected))).rejects.toThrow();
  }
});
