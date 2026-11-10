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

interface CachedOrder { schema: 1; observed_at: string; acquired_at?: string; generation?: string; migrated?: boolean; rows: Row[] }
interface Checkpoint { schema: 2; scope: string; generation: string; retired_at: string | null; refresh_started_at: string | null; orders: Record<string, CachedOrder> }
const MAX_BYTES = 8_000_000;
const GENERATION = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const bytes = (value: string) => new TextEncoder().encode(value).byteLength;

function normalizedCache(raw: unknown, now: number): CachedOrder {
  const value = raw as CachedOrder;
  if (!value || value.schema !== 1 || typeof value.observed_at !== "string"
      || !Number.isFinite(Date.parse(value.observed_at)) || Date.parse(value.observed_at) > now
      || !Array.isArray(value.rows) || value.rows.length > 10_000
      || value.migrated !== undefined && typeof value.migrated !== "boolean"
      || value.generation !== undefined && (typeof value.generation !== "string" || !GENERATION.test(value.generation))
      || value.acquired_at !== undefined && (typeof value.acquired_at !== "string" || !Number.isFinite(Date.parse(value.acquired_at))
        || Date.parse(value.acquired_at) > now)) {
    throw new Error("invalid_order_cache");
  }
  return { schema: 1, observed_at: value.observed_at, acquired_at: value.acquired_at, generation: value.generation,
    migrated: value.migrated, rows: value.rows.map(financialRow) };
}

/** One bounded financial-only checkpoint per report attempt, never per order. */
export class OrderAcquisition {
  progressed = 0;
  private readonly checkpointKey: string;
  private readonly orders = new Map<string, CachedOrder>();
  private readonly sizes = new Map<string, number>();
  private retainedBytes = 0;
  private retiredAt = 0;
  private generation = crypto.randomUUID();
  private refreshStartedAt: number | null = null;
  private invalidatedGeneration: string | null = null;
  private legacyReads = 0;
  private reused = 0;
  private dirty = false;
  private closed = false;
  private ready: Promise<void> | null = null;
  private saving: Promise<void> | null = null;

  constructor(private readonly kv: KVNamespace, private readonly scope: string, private readonly clock = Date.now, private readonly publishedAt?: string) {
    this.checkpointKey = `order_checkpoint:2:${encodeURIComponent(scope)}`;
  }

  private retain(hash: string, cache: CachedOrder): void {
    const size = bytes(JSON.stringify(cache)) + hash.length + 4;
    const total = this.retainedBytes - (this.sizes.get(hash) ?? 0) + size;
    if (total > MAX_BYTES - 512) throw new Error("order_cache_capacity_exceeded");
    this.orders.set(hash, cache); this.sizes.set(hash, size); this.retainedBytes = total;
  }

  private load(): Promise<void> {
    return this.ready ??= (async () => {
      const raw = await this.kv.get(this.checkpointKey);
      if (raw === null) return;
      if (typeof raw === "string" && bytes(raw) > MAX_BYTES) throw new Error("order_cache_capacity_exceeded");
      let priorGeneration: string | null = null;
      try {
        const value = JSON.parse(raw) as Checkpoint;
        if (value.schema !== 2 || value.scope !== this.scope || typeof value.generation !== "string" || !GENERATION.test(value.generation)
            || !value.orders || typeof value.orders !== "object"
            || Array.isArray(value.orders) || Object.keys(value.orders).length > 10_000
            || value.retired_at !== null && (typeof value.retired_at !== "string" || !Number.isFinite(Date.parse(value.retired_at)))) {
          throw new Error("invalid_order_checkpoint");
        }
        const retired = Date.parse(value.retired_at ?? "") || 0;
        if (retired > this.clock()) throw new Error("invalid_order_checkpoint");
        if (value.refresh_started_at != null && (typeof value.refresh_started_at !== "string"
            || !Number.isFinite(Date.parse(value.refresh_started_at)) || Date.parse(value.refresh_started_at) > this.clock())) {
          throw new Error("invalid_order_checkpoint");
        }
        this.retiredAt = retired;
        this.refreshStartedAt = value.refresh_started_at ? Date.parse(value.refresh_started_at) : null;
        for (const [hash, cache] of Object.entries(value.orders)) {
          if (!/^[a-f0-9]{64}$/.test(hash)) throw new Error("invalid_order_checkpoint");
          this.retain(hash, normalizedCache(cache, this.clock()));
        }
        priorGeneration = value.generation;
      } catch (error) {
        if (error instanceof Error && error.message === "order_cache_capacity_exceeded") throw error;
        console.error(JSON.stringify({ event: "finance_order_checkpoint_invalid" }));
        this.orders.clear(); this.sizes.clear(); this.retainedBytes = 0;
        // Unknown retirement authority cannot authorize reuse of expired proofs.
        // All untrusted entries were discarded and legacy reads are disabled.
        // Fresh proofs in this new generation must remain resumable.
        this.retiredAt = 0;
        this.refreshStartedAt = this.clock();
      }
      if (priorGeneration !== null) {
        // Immutable, write-once-valued markers cannot be rolled back by a late
        // partial writer. Visibility is subject to KV's normal convergence.
        const retired = await this.kv.get(this.fenceKey(priorGeneration));
        if (retired === null) this.generation = priorGeneration;
        else if (retired !== "complete") throw new Error("invalid_order_checkpoint");
        const invalidated = await this.kv.get(this.invalidationKey(priorGeneration));
        if (invalidated !== null) {
          if (invalidated !== "invalidated") throw new Error("invalid_order_checkpoint");
          this.orders.clear(); this.sizes.clear(); this.retainedBytes = 0;
          this.generation = crypto.randomUUID(); this.retiredAt = 0;
          this.refreshStartedAt = this.clock(); this.dirty = true;
        }
      }
    })();
  }

  private fenceKey(generation: string): string {
    return `order_retired:2:${encodeURIComponent(this.scope)}:${generation}`;
  }

  private invalidationKey(generation: string): string {
    return `order_invalidated:2:${encodeURIComponent(this.scope)}:${generation}`;
  }

  async prefetch(transactions: string[]): Promise<void> {
    await this.load();
    const hashes = await Promise.all([...new Set(transactions)].map(sha256));
    const wanted = new Set(hashes);
    for (const hash of this.orders.keys()) {
      if (wanted.has(hash)) continue;
      this.retainedBytes -= this.sizes.get(hash)!;
      this.orders.delete(hash); this.sizes.delete(hash); this.dirty = true;
    }
  }

  private async legacy(key: string): Promise<CachedOrder | null> {
    if (this.refreshStartedAt !== null) return null;
    if (this.legacyReads++ >= 128) throw new Error("order_cache_read_limit");
    const value = await this.kv.get(key, "stream");
    if (value === null) return null;
    const reader = new Response(value).body!.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    try {
      while (true) {
        const { value: chunk, done } = await reader.read();
        if (done) break;
        length += chunk.byteLength;
        if (length + this.retainedBytes > MAX_BYTES) throw new Error("order_cache_capacity_exceeded");
        chunks.push(chunk);
      }
    } catch (error) { await reader.cancel(); throw error; }
    finally { reader.releaseLock(); }
    const body = new Uint8Array(length); let at = 0;
    for (const chunk of chunks) { body.set(chunk, at); at += chunk.length; }
    try { return { ...normalizedCache(JSON.parse(new TextDecoder().decode(body)), this.clock()), migrated: true }; }
    catch { console.error(JSON.stringify({ event: "finance_order_cache_invalid" })); return null; }
  }

  private hit(cache: CachedOrder, expected: Row[], invoice: boolean, legacy: boolean): { rows: Row[]; pending: boolean } | null {
    const age = this.clock() - Date.parse(cache.observed_at);
    if (age < 0) throw new Error("invalid_order_cache");
    if (invoice && cache.rows.some(r => r.invoice_event_subtotal_cents === undefined)) throw new Error("invalid_order_cache");
    const current = currentOrderRows(cache.rows, expected);
    const completedAt = Math.max(this.retiredAt, Date.parse(this.publishedAt ?? "") || 0);
    const acquired = Date.parse(cache.acquired_at ?? "");
    const pending = !legacy && !cache.migrated && cache.generation === this.generation
      && Number.isFinite(acquired) && acquired <= this.clock() && acquired > completedAt;
    if (!current.exact || age >= DAY && (!pending || current.foreign)) return null;
    return { rows: current.rows, pending };
  }

  private stage(hash: string, rows: Row[], observedAt: string, acquiredAt = new Date(this.clock()).toISOString(), migrated = false): void {
    this.retain(hash, { schema: 1, observed_at: observedAt, acquired_at: acquiredAt, generation: this.generation, migrated, rows });
    this.dirty = true; this.progressed++;
  }

  async rows(transaction: string, expected: Row[], load: () => Promise<Row[]>): Promise<Row[]> {
    if (this.closed) throw new Error("order_checkpoint_closed");
    await this.load();
    const hash = await sha256(transaction);
    const invoice = transaction.startsWith("invoice:2:");
    const packed = this.orders.get(hash);
    const candidates: Array<() => Promise<{ cache: CachedOrder; legacy: boolean } | null>> = packed
      ? [async () => ({ cache: packed, legacy: false })]
      : [`order_progress:1:${encodeURIComponent(this.scope)}:${hash}`, `order_cache:1:${hash}`].map(key => async () => {
        const cache = await this.legacy(key);
        return cache ? { cache, legacy: true } : null;
      });
    for (const candidate of candidates) {
      const value = await candidate(); // Storage I/O failures propagate.
      if (!value) continue;
      let found: ReturnType<OrderAcquisition["hit"]>;
      try { found = this.hit(value.cache, expected, invoice, value.legacy); }
      catch { console.error(JSON.stringify({ event: "finance_order_cache_invalid" })); continue; }
      if (!found) continue;
      this.reused++;
      if (value.legacy) this.stage(hash, found.rows, value.cache.observed_at,
        value.cache.acquired_at ?? value.cache.observed_at, true);
      else if (!found.pending && !value.cache.migrated) this.stage(hash, found.rows, value.cache.observed_at);
      return found.rows;
    }
    const rows = (await load()).map(financialRow);
    if (invoice && rows.some(r => r.invoice_event_subtotal_cents === undefined)) throw new Error("invoice_schema_changed");
    const current = currentOrderRows(rows, expected);
    if (rows.length > 10_000 || !current.exact) throw new Error("shared_order_line_missing");
    this.stage(hash, current.rows, new Date(this.clock()).toISOString());
    return current.rows;
  }

  refreshAfterContradiction(): boolean {
    const midnight = Date.parse(new Date(this.clock()).toISOString().slice(0, 10) + "T00:00:00Z");
    if (this.closed || !this.reused || this.refreshStartedAt !== null && this.refreshStartedAt >= midnight) return false;
    this.invalidatedGeneration = this.generation;
    this.generation = crypto.randomUUID();
    this.orders.clear(); this.sizes.clear(); this.retainedBytes = 0;
    this.refreshStartedAt = this.clock(); this.dirty = true;
    return true;
  }

  checkpoint(complete = false): Promise<void> {
    if (this.saving) return this.saving;
    this.closed = true;
    return this.saving = (async () => {
      if (complete) {
        await this.load();
        // Persist retirement BEFORE financial publication, including its crash window.
        this.retiredAt = Math.max(this.retiredAt, this.clock(), ...[...this.orders.values()].map(order => Date.parse(order.acquired_at ?? "") || 0));
        this.dirty = true;
      }
      if (!this.dirty) return;
      const value: Checkpoint = { schema: 2, scope: this.scope, generation: this.generation,
        retired_at: this.retiredAt ? new Date(this.retiredAt).toISOString() : null,
        refresh_started_at: this.refreshStartedAt === null ? null : new Date(this.refreshStartedAt).toISOString(),
        orders: Object.fromEntries(this.orders) };
      const body = JSON.stringify(value);
      if (bytes(body) > MAX_BYTES) throw new Error("order_cache_capacity_exceeded");
      if (this.invalidatedGeneration !== null) await this.kv.put(this.invalidationKey(this.invalidatedGeneration), "invalidated");
      await this.kv.put(this.checkpointKey, body);
      if (complete) await this.kv.put(this.fenceKey(this.generation), "complete");
    })();
  }
}
