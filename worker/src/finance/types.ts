// Monetary fields are integer USD cents. These types contain no customer data.
export interface ReceiptSummary {
  entry_cents: number;
  membership_cents: number;
  contribution_cents: number;
  other_cents: number;
  refunded_cents: number;
  net_cents: number;
}

export interface ReceiptBucket {
  days_before: number;
  registrations: number;
  entry_cents: number;
  membership_cents: number;
  contribution_cents: number;
  other_cents: number;
}

export interface ReceiptSnapshot {
  schema: 1;
  family: string;
  year: number;
  tournament_id: string;
  source_as_of: string;
  event_start: string;
  registration_close: string;
  regular_fee_cents: number | null;
  registration_count: number;
  summary: ReceiptSummary;
  // Native fee summaries can exceed recorded manual cash. Keep both amounts
  // and the explicit correction; cash order totals own the receipt amount.
  native_summary?: ReceiptSummary;
  manual_cash_adjustment_cents?: number;
  // One id/time per registration, hashed before storage; no names or contact data.
  cohort: Array<{ id: string; paid_at: string }>;
  buckets: ReceiptBucket[];
  previous_net_cents: number | null;
  previous_as_of: string | null;
}

export interface ReceiptCard {
  family: string;
  year: number;
  status: string;
  event_start?: string | null;
  event_end?: string | null;
  registration_close?: string | null;
  regular_fee?: number | null;
  current_count: number;
  point_estimate?: number | null;
  count_observed_at?: string | null;
  count_cohort_hash?: string | null;
}

export interface ReceiptValue {
  family: string;
  year: number;
  value: number | null;
  basis: "chess_action_receipts";
  missing: string | null;
  actual_cents: number | null;
  future_cents: number | null;
  refund_reserve_cents: number | null;
  source_as_of: string | null;
  model_observed_at: string | null;
  stale: boolean;
  coverage: "chess_action";
  confidence: "family" | "pooled" | null;
  last_day: { value: number; span: number } | null;
}

export const FINANCE_MAX_AGE_MS = 36 * 3_600_000;
export const snapshotKey = (family: string, year: number) => `receipts:${encodeURIComponent(family)}:${year}`;

export function cents(value: unknown): number {
  if (typeof value !== "number" && typeof value !== "string") throw new Error("invalid_money");
  const formatted = String(value).trim();
  if (!/^\$?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?$/.test(formatted)) throw new Error("invalid_money");
  const text = formatted.replace(/[$,]/g, "");
  const [whole, part = ""] = text.split(".");
  const n = Number(whole) * 100 + Number(part.padEnd(2, "0"));
  if (!Number.isSafeInteger(n)) throw new Error("invalid_money");
  return n;
}

export function reconcileSummary(s: ReceiptSummary): void {
  if (!Object.values(s).every(n => Number.isSafeInteger(n) && n >= 0)
      || s.entry_cents + s.membership_cents + s.contribution_cents + s.other_cents
        - s.refunded_cents !== s.net_cents) throw new Error("summary_mismatch");
}

export async function sha256(text: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function cohortHash(ids: string[]): Promise<string> {
  if (new Set(ids).size !== ids.length) throw new Error("duplicate_registration");
  // Public scraper uses the same sorted hash-of-hashes representation.
  return sha256([...ids].sort().join("\n"));
}

export function validateSnapshot(raw: unknown): ReceiptSnapshot {
  if (!raw || typeof raw !== "object") throw new Error("invalid_snapshot");
  const s = raw as ReceiptSnapshot;
  if (s.schema !== 1 || typeof s.family !== "string" || !Number.isInteger(s.year)
      || !/^\d+$/.test(s.tournament_id) || !Number.isFinite(Date.parse(s.source_as_of))
      || !/^\d{4}-\d{2}-\d{2}$/.test(s.event_start)
      || !/^\d{4}-\d{2}-\d{2}$/.test(s.registration_close)
      || !s.summary || typeof s.summary !== "object" || !Array.isArray(s.cohort) || !Array.isArray(s.buckets)
      || !Number.isInteger(s.registration_count) || s.registration_count < 0
      || s.cohort.some(r => !r || !/^[a-f0-9]{64}$/.test(r.id) || !Number.isFinite(Date.parse(r.paid_at)))
      || s.buckets.some(b => !b || !Number.isFinite(b.days_before) || !Number.isInteger(b.registrations)
        || b.registrations < 0 || ![b.entry_cents, b.membership_cents, b.contribution_cents, b.other_cents]
          .every(n => Number.isSafeInteger(n) && n >= 0))
      || (s.regular_fee_cents !== null && (!Number.isSafeInteger(s.regular_fee_cents) || s.regular_fee_cents <= 0))) {
    throw new Error("invalid_snapshot");
  }
  reconcileSummary(s.summary);
  if (s.native_summary !== undefined || s.manual_cash_adjustment_cents !== undefined) {
    const adjustment = s.manual_cash_adjustment_cents;
    if (!s.native_summary || !Number.isSafeInteger(adjustment) || adjustment! < 0) throw new Error("invalid_snapshot");
    reconcileSummary(s.native_summary);
    for (const field of ["entry_cents", "membership_cents", "contribution_cents", "other_cents", "refunded_cents", "net_cents"] as const) {
      if (s.native_summary[field] - (field === "entry_cents" || field === "net_cents" ? adjustment! : 0) !== s.summary[field]) throw new Error("invalid_snapshot");
    }
  }
  if (new Set(s.cohort.map(r => r.id)).size !== s.cohort.length) throw new Error("duplicate_registration");
  return s;
}
