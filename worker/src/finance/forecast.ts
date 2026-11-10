import { cohortHash, FINANCE_MAX_AGE_MS, reconcileSummary } from "./types";
import type { ReceiptCard, ReceiptSnapshot, ReceiptValue } from "./types";

const DAY = 86_400_000;

export async function receiptForecast(
  card: ReceiptCard,
  snapshot: ReceiptSnapshot | null,
  history: ReceiptSnapshot[],
  now = Date.now(),
): Promise<ReceiptValue> {
  const out: ReceiptValue = {
    family: card.family, year: card.year, value: null, basis: "chess_action_receipts",
    missing: null, actual_cents: null, future_cents: null, refund_reserve_cents: null,
    source_as_of: snapshot?.source_as_of ?? null, model_observed_at: card.count_observed_at ?? null,
    stale: false, coverage: "chess_action", confidence: null, last_day: null,
  };
  const fail = (reason: string) => ({ ...out, missing: reason });
  if (!snapshot) return fail("no_receipts");
  if (snapshot.family !== card.family || snapshot.year !== card.year) return fail("edition_mismatch");
  reconcileSummary(snapshot.summary);
  out.actual_cents = snapshot.summary.net_cents;
  const sourceTime = Date.parse(snapshot.source_as_of);
  const modelTime = Date.parse(card.count_observed_at ?? "");
  out.stale = now - sourceTime > FINANCE_MAX_AGE_MS || now - modelTime > FINANCE_MAX_AGE_MS;
  if (out.stale || sourceTime > now + 60_000 || !Number.isFinite(modelTime) || modelTime > now + 60_000) {
    return fail(out.stale ? "stale_source" : "unmatched_count");
  }
  // Independent refreshes may observe the same exact identity set in either order.
  // Freshness and the count/hash proof below own compatibility; wall-clock order
  // alone must not invalidate unchanged registrations.
  const observed = snapshot.cohort.filter(r => Date.parse(r.paid_at) <= modelTime);
  if (snapshot.cohort.length !== snapshot.registration_count || observed.length !== card.current_count || !card.count_cohort_hash
      || await cohortHash(observed.map(r => r.id)) !== card.count_cohort_hash) return fail("unmatched_count");
  if (!Number.isInteger(card.point_estimate) || card.point_estimate! < 0) return fail("no_forecast");

  // All source registrations since the model observation are already in actuals.
  const remaining = Math.max(0, card.point_estimate! - snapshot.cohort.length);
  const horizon = (Date.parse(snapshot.event_start + "T00:00:00Z") - sourceTime) / DAY;
  // Never train on the target/future edition, or an event still taking entries.
  const eligible = history.filter(h => (h.family === card.family ? h.year < card.year : h.year <= card.year)
    && h.registration_close !== null && Date.parse(h.registration_close + "T23:59:59Z") < sourceTime
    && h.registration_count > 0 && h.regular_fee_cents && h.summary.net_cents >= 0);
  let selected = eligible.filter(h => h.family === card.family).sort((a, b) => b.year - a.year).slice(0, 2);
  out.confidence = selected.length ? "family" : "pooled";
  if (!selected.length) selected = eligible;
  if (!selected.length) return fail("no_history");
  const regular = card.regular_fee;
  if (remaining && (typeof regular !== "number" || !Number.isFinite(regular) || regular <= 0)) return fail("no_fee");
  let registrations = 0;
  let futureReceipts = 0;
  for (const h of selected) {
    for (const b of h.buckets.filter(b => b.days_before <= horizon)) {
      const scale = remaining ? regular! * 100 / h.regular_fee_cents! : 1;
      // Receipt yield is BEFORE refunds; zero-dollar registrations remain in the divisor.
      futureReceipts += (b.entry_cents + b.contribution_cents) * scale
        + b.membership_cents + b.other_cents;
      registrations += b.registrations;
    }
  }
  if (remaining && !registrations) return fail("no_history");
  out.future_cents = remaining ? Math.round(remaining * futureReceipts / registrations) : 0;
  const historicGross = selected.reduce((n, h) => n + h.summary.net_cents + h.summary.refunded_cents, 0);
  if (!historicGross) return fail("no_history");
  const refundRate = selected.reduce((n, h) => n + h.summary.refunded_cents, 0) / historicGross;
  const lifetimeRefund = Math.round((snapshot.summary.net_cents + snapshot.summary.refunded_cents + out.future_cents) * refundRate);
  out.refund_reserve_cents = Math.max(0, lifetimeRefund - snapshot.summary.refunded_cents);
  out.value = (out.actual_cents + out.future_cents - out.refund_reserve_cents) / 100;
  if (snapshot.previous_as_of && Number.isSafeInteger(snapshot.previous_net_cents)) {
    const span = (sourceTime - Date.parse(snapshot.previous_as_of)) / DAY;
    if (span >= 0.5 && span <= 2) out.last_day = {
      value: (snapshot.summary.net_cents - snapshot.previous_net_cents!) / 100, span: Math.round(span),
    };
  }
  return out;
}
