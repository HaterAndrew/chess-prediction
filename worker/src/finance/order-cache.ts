import { cents, sha256 } from "./types";

type Row = Record<string, unknown>;
const MONEY = ["section_amount", "membership_amount", "secmembership_amount", "other_fees", "order_value", "paypal_credit_card_fee_contribution", "public_discount_amount", "discount_amount"] as const;
const DAY = 86_400_000;
const text = (value: unknown) => value === null || value === undefined ? "" : String(value).trim();

/** Keep financial evidence only; never cache contact data or transaction strings. */
function financialRow(row: Row): Row {
  const result: Row = {};
  for (const key of ["order_id", "tournament", "section", "payment_date", "payment_time", "payment_type", "is_deleted"] as const) result[key] = text(row[key]);
  const deletion = row.is_deleted === false ? "0" : row.is_deleted === true ? "1" : text(row.is_deleted);
  result.is_deleted = ["", "0", "No"].includes(deletion) ? "" : "1";
  if (!/^\d+$/.test(String(result.order_id)) || !/^\d{4}\s[^\r\n]{1,240}$/.test(String(result.tournament))
      || !/^\d{4}-\d{2}-\d{2}$/.test(String(result.payment_date)) || !/^\d{2}:\d{2}:\d{2}$/.test(String(result.payment_time))
      || !/^\d{0,3}$/.test(String(result.payment_type)) || String(result.section).length > 240) throw new Error("source_schema_changed");
  const status = text(row.status);
  result.status = ["Approved", "Manual", "Free Registration", "Pending", "Declined"].includes(status) ? status : "Unrecognized";
  const transaction = text(row.paypal_trans_id);
  result.paypal_trans_id = /credit/i.test(transaction) ? "Credit" : /transfer/i.test(transaction) ? "Transfer"
    : transaction.toLowerCase() === "cash" ? "Cash" : "";
  for (const key of MONEY) {
    const amount = row[key] === "" || row[key] === null || row[key] === undefined ? 0 : cents(row[key]);
    result[key] = `${Math.floor(amount / 100)}.${String(amount % 100).padStart(2, "0")}`;
  }
  if (row.invoice_event_subtotal_cents !== undefined) {
    if (!Number.isSafeInteger(row.invoice_event_subtotal_cents) || Number(row.invoice_event_subtotal_cents) < 0) throw new Error("invoice_schema_changed");
    result.invoice_event_subtotal_cents = row.invoice_event_subtotal_cents;
  }
  return result;
}

function signature(row: Row): string {
  const normalized = financialRow(row);
  // The source prints an order's contribution on only one report row; its
  // position can differ between the selected-event and full-order reports.
  delete normalized.paypal_credit_card_fee_contribution;
  delete normalized.invoice_event_subtotal_cents;
  return JSON.stringify(normalized);
}

function currentOrderRows(rows: Row[], expected: Row[]): { rows: Row[]; foreign: boolean; exact: boolean } {
  const orders = new Set(expected.map(r => text(r.order_id)));
  const events = new Set(expected.map(r => text(r.tournament)));
  const selected = rows.filter(r => orders.has(text(r.order_id)));
  const own = selected.filter(r => events.has(text(r.tournament)));
  const counts = new Map<string, number>();
  for (const row of own) { const id = signature(row); counts.set(id, (counts.get(id) ?? 0) + 1); }
  let exact = own.length === expected.length;
  for (const row of expected) {
    const id = signature(row); const remaining = counts.get(id) ?? 0;
    if (!remaining) { exact = false; break; }
    counts.set(id, remaining - 1);
  }
  return { rows: selected, foreign: selected.length !== own.length, exact };
}

interface CachedOrder { schema: 1; observed_at: string; acquired_at?: string; rows: Row[] }

export class OrderAcquisition {
  progressed = 0;
  private readonly doneKey: string;
  private done: Promise<number> | null = null;
  private readonly prefetched = new Map<string, string | null>();
  private readonly acquiredAt: string;

  constructor(private readonly kv: KVNamespace, private readonly scope: string, private readonly clock = Date.now, private readonly publishedAt?: string) {
    this.acquiredAt = new Date(this.clock()).toISOString();
    this.doneKey = `order_progress_done:1:${encodeURIComponent(scope)}`;
  }

  async prefetch(transactions: string[]): Promise<void> {
    const hashes = await Promise.all([...new Set(transactions)].map(sha256));
    const keys = hashes.flatMap(hash => [`order_progress:1:${encodeURIComponent(this.scope)}:${hash}`, `order_cache:1:${hash}`]);
    let retainedBytes = 0;
    for (let start = 0; start < keys.length; start += 100) {
      const found = await this.kv.get(keys.slice(start, start + 100), "text");
      for (const key of keys.slice(start, start + 100)) {
        const raw = found.get(key) ?? null;
        retainedBytes += raw === null ? 0 : new TextEncoder().encode(raw).byteLength;
        if (retainedBytes > 8_000_000) {
          this.prefetched.clear();
          throw new Error("order_cache_capacity_exceeded");
        }
        this.prefetched.set(key, raw);
      }
    }
  }

  async rows(transaction: string, expected: Row[], load: () => Promise<Row[]>): Promise<Row[]> {
    const hash = await sha256(transaction);
    const freshKey = `order_cache:1:${hash}`;
    const progressKey = `order_progress:1:${encodeURIComponent(this.scope)}:${hash}`;
    this.done ??= this.kv.get(this.doneKey).then(raw => Math.max(Date.parse(raw ?? "") || 0, Date.parse(this.publishedAt ?? "") || 0));
    const completedAt = await this.done;
    const now = this.clock();
    for (const key of [progressKey, freshKey]) {
      const raw = this.prefetched.has(key) ? this.prefetched.get(key)! : await this.kv.get(key);
      if (raw === null) continue;
      let hit: { rows: Row[]; observedAt: string } | null = null;
      try {
        const cache = JSON.parse(raw) as CachedOrder;
        const age = now - Date.parse(cache.observed_at);
        if (cache.schema !== 1 || !Number.isFinite(age) || age < 0 || !Array.isArray(cache.rows) || cache.rows.length > 10_000) throw new Error("invalid_order_cache");
        const normalized = cache.rows.map(financialRow);
        if (transaction.startsWith("invoice:2:") && normalized.some(r => r.invoice_event_subtotal_cents === undefined)) throw new Error("invalid_order_cache");
        const current = currentOrderRows(normalized, expected);
        const pending = key === progressKey && Number.isFinite(Date.parse(cache.acquired_at ?? ""))
          && Date.parse(cache.acquired_at!) > (Number.isFinite(completedAt) ? completedAt : 0);
        if (!current.exact || (age >= DAY && (!pending || current.foreign))) continue;
        hit = { rows: current.rows, observedAt: cache.observed_at };
      } catch {
        console.error(JSON.stringify({ event: "finance_order_cache_invalid" }));
      }
      if (hit) {
        if (key === freshKey) await this.stage(progressKey, hit.rows, hit.observedAt);
        return hit.rows;
      }
    }
    const rows = (await load()).map(financialRow);
    if (transaction.startsWith("invoice:2:") && rows.some(r => r.invoice_event_subtotal_cents === undefined)) throw new Error("invoice_schema_changed");
    const current = currentOrderRows(rows, expected);
    if (rows.length > 10_000 || !current.exact) throw new Error("shared_order_line_missing");
    const observedAt = new Date(this.clock()).toISOString();
    const body = JSON.stringify({ schema: 1, observed_at: observedAt, rows });
    if (new TextEncoder().encode(body).byteLength > 8_000_000) throw new Error("source_too_many_rows");
    await this.kv.put(freshKey, body, { expirationTtl: 86400 });
    await this.stage(progressKey, current.rows, observedAt);
    return current.rows;
  }

  private async stage(key: string, rows: Row[], observedAt: string): Promise<void> {
    await this.kv.put(key, JSON.stringify({ schema: 1, observed_at: observedAt, acquired_at: this.acquiredAt, rows }));
    this.progressed++;
  }

  async committed(): Promise<void> {
    // The published snapshot timestamp independently retires this run. This
    // marker also retires progress if the snapshot is subsequently damaged.
    try { await this.kv.put(this.doneKey, new Date(this.clock()).toISOString()); }
    catch { console.error(JSON.stringify({ event: "finance_order_progress_retirement_failed" })); }
  }
}
