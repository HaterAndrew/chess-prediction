import { describe, expect, it } from "vitest";
import { buildReceiptSnapshot } from "./report";
import { cohortHash, sha256 } from "./types";
import { matchTournament } from "./editions";
import { receiptForecast } from "./forecast";
import type { ReceiptCard, ReceiptSummary } from "./types";

const AS_OF = "2026-11-09T02:30:00Z";
function row(extra: Record<string, unknown> = {}) {
  return { order_id: "900", player_id: "1", invoicenumber: "synthetic-invoice", paypal_trans_id: "synthetic-transaction",
    tournament: "2026 Example Open", section: "Open", status: "Approved", section_amount: "10.00", membership_amount: "0.00",
    other_fees: "", public_discount_amount: "", discount_amount: "", paypal_credit_card_fee_contribution: "",
    order_value: "10.00", payment_date: "2026-11-08", payment_time: "12:00:00", is_deleted: "", is_refunded: "",
    player_email: "synthetic@example.invalid", ...extra };
}
async function card(): Promise<ReceiptCard> {
  return { family: "Example Open", year: 2026, status: "live", current_count: 1, point_estimate: 2,
    event_start: "2026-11-14", registration_close: "2026-11-15", regular_fee: 10,
    count_observed_at: "2026-11-09T01:15:00Z", count_cohort_hash: await cohortHash([await sha256("1")]) };
}
const summary = (extra: Partial<ReceiptSummary> = {}): ReceiptSummary => ({
  entry_cents: 1000, membership_cents: 0, other_cents: 0, contribution_cents: 0, refunded_cents: 0, net_cents: 1000, ...extra,
});

describe("native order accounting", () => {
  it("refuses an unverified secondary membership even when a discount offsets it", async () => {
    await expect(buildReceiptSnapshot(await card(), "123", [row({ secmembership_amount: "1.00" })], summary(), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("secondary_membership_requires_reconciliation");
  });
  it("uses each invoice event subtotal when cross-event discounts cancel in aggregate", async () => {
    const target = { ...await card(), year: 2025, status: "complete", event_start: "2025-11-14", registration_close: "2025-11-15", regular_fee: 100, count_cohort_hash: null };
    const first = row({ tournament: "2025 Example Open", section_amount: "100.00", order_value: "150.00", payment_date: "2025-11-04", paypal_trans_id: "first", invoice_event_subtotal_cents: 5000 });
    const second = row({ order_id: "901", player_id: "2", tournament: "2025 Example Open", section_amount: "100.00", order_value: "150.00", payment_date: "2025-11-13", paypal_trans_id: "second", invoice_event_subtotal_cents: 10000 });
    const result = await buildReceiptSnapshot(target, "123", [first, second], summary({ entry_cents: 15000, net_cents: 15000 }), AS_OF,
      async transaction => { const own = transaction === "first" ? first : second; return [own, { ...own, tournament: "2025 Another Open", invoice_event_subtotal_cents: transaction === "first" ? 10000 : 5000 }]; });
    expect(result.buckets.find(b => b.days_before === 9.5)?.entry_cents).toBe(5000);
    expect(result.buckets.find(b => b.days_before === 0.5)?.entry_cents).toBe(10000);
  });
  it("checks complete membership even when outside fees and discounts cancel", async () => {
    const target = row();
    const outside = row({ tournament: "2026 Another Open", section_amount: "5.00", public_discount_amount: "5.00" });
    let requests = 0;
    await buildReceiptSnapshot(await card(), "123", [target], summary(), AS_OF,
      async () => { requests++; return [target, outside]; });
    expect(requests).toBe(1);
  });
  it("derives an omitted cart discount once from the complete paid order", async () => {
    const first = row({ section_amount: "12.00", order_value: "22.00" });
    const second = { ...first, player_id: "2", uscf_id: "87654321" };
    const result = await buildReceiptSnapshot(await card(), "123", [first, second], summary({ entry_cents: 2200, net_cents: 2200 }), AS_OF,
      async () => [first, second]);
    expect(result.summary.entry_cents).toBe(2200);
    expect(result.manual_cash_adjustment_cents).toBeUndefined();
    expect(result.buckets[0].entry_cents).toBe(2200);
  });
  it("uses a contribution present only on another event's full-order row", async () => {
    const first = row({ order_value: "31.00" });
    const second = { ...first, player_id: "2", tournament: "2026 Another Open", section_amount: "20.00", paypal_credit_card_fee_contribution: "1.00" };
    const result = await buildReceiptSnapshot(await card(), "123", [first], summary({ contribution_cents: 33, net_cents: 1033 }), AS_OF,
      async () => [first, second]);
    expect(result.buckets[0].contribution_cents).toBe(33);
  });
  it("proves a source/public federation join against the observed public-ID hash", async () => {
    const source = row({ uscf_id: "12345678" });
    delete (source as Record<string, unknown>).player_id;
    const target = { ...await card(), count_cohort_hash: await cohortHash([await sha256("101")]) };
    const result = await buildReceiptSnapshot(target, "123", [source], summary(), AS_OF, async (_transaction, expected) => expected,
      async () => [{ id: "101", uscf: "12345678", fide: "" }]);
    expect(result.cohort[0].id).toBe(await sha256("101"));
    const mismatch = await buildReceiptSnapshot(target, "123", [source], summary(), AS_OF, async (_transaction, expected) => expected,
      async () => [{ id: "102", uscf: "12345678", fide: "" }]);
    expect(mismatch.cohort).toEqual([]);
  });
  it("uses recorded manual cash and retains the native fee discrepancy explicitly", async () => {
    const cash = row({ status: "Manual", payment_type: "0", paypal_trans_id: "Cash",
      section_amount: "128.00", order_value: "123.00" });
    const result = await buildReceiptSnapshot(await card(), "123", [cash],
      summary({ entry_cents: 12800, net_cents: 12800 }), AS_OF, async () => [cash]);
    expect(result.summary.net_cents).toBe(12300);
    expect(result.native_summary!.net_cents).toBe(12800);
    expect(result.manual_cash_adjustment_cents).toBe(500);
    expect(result.buckets[0]).toMatchObject({ registrations: 1, entry_cents: 12300 });
  });
  it("reads a repeated cash transaction label once and keeps orders distinct", async () => {
    const first = row({ status: "Manual", payment_type: "0", paypal_trans_id: "Cash", section_amount: "128.00", order_value: "123.00" });
    const second = { ...first, order_id: "901", player_id: "2" };
    let requests = 0;
    const result = await buildReceiptSnapshot(await card(), "123", [first, second], summary({ entry_cents: 25600, net_cents: 25600 }), AS_OF,
      async () => { requests++; return [first, second]; });
    expect(requests).toBe(1);
    expect(result.summary.net_cents).toBe(24600);
    expect(result.manual_cash_adjustment_cents).toBe(1000);
  });
  it("counts a verified zero-money free registration in the yield divisor", async () => {
    const free = row({ status: "Free Registration", section_amount: "0.00", order_value: "0.00" });
    const result = await buildReceiptSnapshot(await card(), "123", [free], summary({ entry_cents: 0, net_cents: 0 }), AS_OF, async (_transaction, expected) => expected);
    expect(result.buckets[0]).toMatchObject({ registrations: 1, entry_cents: 0 });
  });
  it("does not treat unknown manual payments, positive free fees or cross-event cash discrepancies as received", async () => {
    await expect(buildReceiptSnapshot(await card(), "123", [row({ status: "Manual", payment_type: "0", paypal_trans_id: "Check" })], summary(), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("unreconciled_payment_status");
    await expect(buildReceiptSnapshot(await card(), "123", [row({ status: "Manual", payment_type: "0", paypal_trans_id: "Cash due tomorrow" })], summary(), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("unreconciled_payment_status");
    await expect(buildReceiptSnapshot(await card(), "123", [row({ status: "Free Registration" })], summary(), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("unreconciled_payment_status");
    const cash = row({ status: "Manual", payment_type: "0", paypal_trans_id: "Cash", section_amount: "128.00", order_value: "250.00" });
    await expect(buildReceiptSnapshot(await card(), "123", [cash], summary({ entry_cents: 12800, net_cents: 12800 }), AS_OF,
      async () => [cash, { ...cash, player_id: "2", tournament: "2026 Another Open" }]))
      .rejects.toThrow("shared_order_reconciliation_failed");
  });
  it("handles a discount belonging only to another tournament in the same order", async () => {
    const target = row({ order_value: "20.00" });
    const other = row({ player_id: "2", tournament: "2026 Another Open", section_amount: "20.00", public_discount_amount: "10.00", order_value: "20.00" });
    const snapshot = await buildReceiptSnapshot(await card(), "123", [target], summary(), AS_OF, async () => [target, other]);
    expect(snapshot.summary.net_cents).toBe(1000);
  });
  it("keeps residual event pennies stable when full-order rows are reordered", async () => {
    const target = row({ order_value: "20.01", paypal_credit_card_fee_contribution: "0.01" });
    const other = row({ player_id: "2", tournament: "2026 Another Open", order_value: "20.01", paypal_credit_card_fee_contribution: "0.01" });
    const a = await buildReceiptSnapshot(await card(), "123", [target], summary(), AS_OF, async () => [target, other]);
    const b = await buildReceiptSnapshot(await card(), "123", [target], summary(), AS_OF, async () => [other, target]);
    expect(a.buckets).toEqual(b.buckets);
  });
  it("excludes historical payments before the current precise horizon", async () => {
    const targetCard = await card();
    const target = await buildReceiptSnapshot(targetCard, "123", [row()], summary(), AS_OF, async (_transaction, expected) => expected);
    const historic = await buildReceiptSnapshot({ ...targetCard, year: 2025, status: "complete", event_start: "2025-11-14", registration_close: "2025-11-15", count_cohort_hash: null }, "122", [
      row({ tournament: "2025 Example Open", payment_date: "2025-11-08", section_amount: "20.00", order_value: "20.00" }),
      row({ tournament: "2025 Example Open", order_id: "901", player_id: "2", payment_date: "2025-11-12" }),
    ], summary({ entry_cents: 3000, net_cents: 3000 }), AS_OF, async (_transaction, expected) => expected);
    expect((await receiptForecast(targetCard, target, [historic], Date.parse(AS_OF))).future_cents).toBe(1000);
  });
  it("proves registration identity and drops personal information before storage", async () => {
    const result = await buildReceiptSnapshot(await card(), "123", [row()], summary(), AS_OF, async (_transaction, expected) => expected);
    expect(result.registration_count).toBe(1);
    expect(result.cohort[0].id).toBe(await sha256("1"));
    expect(JSON.stringify(result)).not.toContain("synthetic@example.invalid");
    expect(JSON.stringify(result)).not.toContain("synthetic-transaction");
  });
  it("deducts cart discounts once and keeps refunds separate", async () => {
    const result = await buildReceiptSnapshot(await card(), "123", [row({
      section_amount: "12.00", public_discount_amount: "2.00", is_refunded: "Yes",
    })], summary({ refunded_cents: 200, net_cents: 800 }), AS_OF, async (_transaction, expected) => expected);
    expect(result.buckets[0].entry_cents).toBe(1000);
    expect(result.summary.net_cents).toBe(800);
    expect(result.registration_count).toBe(1);
  });
  it("allocates a shared-order contribution using all original cash lines", async () => {
    const target = row({ order_value: "31.01", paypal_credit_card_fee_contribution: "1.01" });
    const other = row({ player_id: "2", tournament: "2026 Another Open", section_amount: "20.00", order_value: "31.01", paypal_credit_card_fee_contribution: "1.01" });
    const result = await buildReceiptSnapshot(await card(), "123", [target], summary({ contribution_cents: 34, net_cents: 1034 }), AS_OF, async () => [target, other]);
    expect(result.buckets[0].contribution_cents).toBe(34);
    await expect(buildReceiptSnapshot(await card(), "123", [target], summary(), AS_OF, async () => []))
      .rejects.toThrow("shared_order_reconciliation_failed");
  });
  it("retains cash from deleted records without adding a current registration", async () => {
    const result = await buildReceiptSnapshot(await card(), "123", [row({ is_deleted: "Yes" })], summary(), AS_OF, async (_transaction, expected) => expected);
    expect(result.registration_count).toBe(0);
    expect(result.buckets[0]).toMatchObject({ registrations: 0, entry_cents: 1000 });
  });
  it("does not accept pending payments or positive credit redemptions as cash", async () => {
    await expect(buildReceiptSnapshot(await card(), "123", [row({ status: "Pending" })], summary(), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("unreconciled_payment_status");
    await expect(buildReceiptSnapshot(await card(), "123", [row({ paypal_trans_id: "Credit" })], summary(), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("credit_provenance_required");
  });
  it("requires native-summary reconciliation rather than trusting individual fee cells", async () => {
    await expect(buildReceiptSnapshot(await card(), "123", [row()], summary({ membership_cents: 100 }), AS_OF, async (_transaction, expected) => expected))
      .rejects.toThrow("receipt_reconciliation_failed");
  });
  it("does not collapse World Open section groups or successive editions", () => {
    expect(matchTournament({ family: "World Open top 6 sections", year: 2026 } as ReceiptCard, [
      { id: "1", title: "2026 World Open, lower sections" }, { id: "2", title: "2026 World Open, top 6 sections" },
      { id: "3", title: "2025 World Open, top 6 sections" },
    ])).toBe("2");
  });
});
