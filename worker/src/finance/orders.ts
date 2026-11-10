import type { InvoiceDiscountEvidence } from "./types";
import type { ChessActionClient } from "./client";
import type { OrderAcquisition } from "./order-cache";
import { invoiceContainsWholeOrder } from "./invoice";

type Row = Record<string, unknown>;
export function invoiceCacheKey(row: Row): string {
  const id = String(row.order_id ?? "");
  if (!/^\d{1,40}$/.test(id)) throw new Error("order_identity_missing");
  return `invoice:2:${id}`;
}

export async function acquireCartRows(client: ChessActionClient, acquisition: OrderAcquisition, transaction: string, expected: Row[]): Promise<Row[]> {
  const groups = new Map<string, Row[]>();
  for (const row of expected) {
    const key = invoiceCacheKey(row);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const result: Row[] = [];
  for (const [key, part] of groups) {
    const id = String(part[0].order_id);
    result.push(...await acquisition.rows(key, part, async () => {
      const invoice = await client.invoice(id);
      const totals = new Map<string, number>();
      const adjustments = new Map<string, InvoiceDiscountEvidence>();
      const withEvidence = (rows: Row[]) => rows.map(row => {
        const subtotal = totals.get(String(row.tournament ?? "").replace(/\s+/g, " ").trim());
        if (subtotal === undefined) throw new Error("invoice_schema_changed");
        const adjustment = adjustments.get(String(row.tournament ?? "").replace(/\s+/g, " ").trim());
        return { ...row, invoice_event_subtotal_cents: subtotal, ...(adjustment ? { invoice_discount_variant: adjustment.variant,
          invoice_discount_cents: adjustment.discount_cents, invoice_net_order_cents: adjustment.net_order_cents } : {}) };
      });
      if (await invoiceContainsWholeOrder(invoice, part, totals, adjustments)) return withEvidence(part);
      // Cross-event cash discrepancies remain unverified; do not scan years
      // of unrelated Cash transactions or claim a complete selected cart.
      if (transaction.trim().toLowerCase() === "cash") throw new Error("shared_order_details_required");
      const full = await client.playerRows("All", transaction, [id]);
      if (!await invoiceContainsWholeOrder(invoice, full, totals, adjustments)) throw new Error("shared_order_line_missing");
      return withEvidence(full);
    }));
  }
  return result;
}
