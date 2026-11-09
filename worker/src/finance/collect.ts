import { ChessActionClient } from "./client";
import { matchTournament } from "./editions";
import { receiptForecast } from "./forecast";
import { parseSummary, tournamentOptions } from "./html";
import { buildReceiptSnapshot } from "./report";
import { parsePublicRegistrations } from "./public-cohort";
import { OrderAcquisition } from "./order-cache";
import { acquireCartRows, invoiceCacheKey } from "./orders";
import { readHistory, readSnapshot, readCalibration, invalidHistory } from "./store";
import { calendarDate, snapshotKey, validateSnapshot } from "./types";
import type { ReceiptCard, ReceiptSnapshot } from "./types";

export interface FinanceEnv {
  FINANCE_KV: KVNamespace;
  CHESS_ACTION_COOKIE?: string;
}

const DAY = 86_400_000;
const SOURCE_ERRORS = new Set([
  "source_login_expired", "source_login_failed", "source_session_invalid", "source_network_failed",
  "source_timeout",
  "source_http_failed", "source_schema_changed", "source_incomplete", "source_request_limit",
  "source_changed_during_read", "source_read_failed", "source_too_many_rows", "source_destination_refused",
  "unmapped_tournament", "ambiguous_tournament", "incompatible_edition", "summary_schema_changed", "summary_mismatch",
  "unreconciled_payment_status", "credit_provenance_required", "order_identity_missing",
  "entry_reconciliation_failed", "discount_reconciliation_failed", "order_reconciliation_failed",
  "shared_order_details_required", "shared_order_reconciliation_failed", "shared_order_line_missing",
  "receipt_reconciliation_failed", "payment_date_missing", "event_calendar_missing",
  "report_edition_mismatch", "ambiguous_registration_identity", "invalid_money", "invalid_snapshot",
  "public_registration_unavailable", "public_registration_schema_changed",
  "secondary_membership_requires_reconciliation", "order_cache_capacity_exceeded", "invoice_schema_changed",
]);
export const safeFailure = (error: unknown) => error instanceof Error && SOURCE_ERRORS.has(error.message) ? error.message : "collection_failed";

async function rememberHistory(kv: KVNamespace, snapshot: ReceiptSnapshot): Promise<void> {
  const own = await readHistory(kv, snapshot.family).catch(error => {
    if (!invalidHistory(error)) throw error;
    console.error(JSON.stringify({ event: "finance_calibration_cache_rebuilt", cache: "family" }));
    return [];
  });
  const pooled = await readHistory(kv, "pooled").catch(error => {
    if (!invalidHistory(error)) throw error;
    console.error(JSON.stringify({ event: "finance_calibration_cache_rebuilt", cache: "pooled" }));
    // Derived cache: reseed from independently validated family history and
    // this reconciled source report. Other families return as they refresh.
    return own;
  });
  for (const family of [snapshot.family, "pooled"]) {
    const history = (family === "pooled" ? pooled : own).filter(h => h.family !== snapshot.family || h.year !== snapshot.year);
    history.push(snapshot);
    history.sort((a, b) => b.year - a.year);
    await kv.put(`history:${encodeURIComponent(family)}`, JSON.stringify(history.slice(0, family === "pooled" ? 128 : 2)));
  }
}

export async function collectBatch(env: FinanceEnv, cards: ReceiptCard[], now = Date.now(), client = new ChessActionClient()): Promise<{ collected: number; failed: number }> {
  if (!env.FINANCE_KV) throw new Error("finance_storage_missing");
  const attemptedAt = new Date(now).toISOString();
  const wallStartedAt = Date.now();
  // A fresh password login sends email codes. It is deliberately never used by
  // scheduled work. An expired session requires the one-time terminal helper.
  if (!env.CHESS_ACTION_COOKIE) {
    await env.FINANCE_KV.put("collector:status", JSON.stringify({ attempted_at: attemptedAt, ok: false, reason: "source_session_required" }));
    return { collected: 0, failed: 1 };
  }
  let options: Array<{ id: string; title: string }>;
  try {
    options = await tournamentOptions(await client.resume(env.CHESS_ACTION_COOKIE));
  } catch (error) {
    await env.FINANCE_KV.put("collector:status", JSON.stringify({ attempted_at: attemptedAt, ok: false, reason: safeFailure(error) }));
    return { collected: 0, failed: 1 };
  }
  const needed: Array<{ card: ReceiptCard; previous: Awaited<ReturnType<typeof readSnapshot>>; priority: number; attempted: string }> = [];
  const midnight = Date.parse(attemptedAt.slice(0, 10) + "T00:00:00Z");
  const families = new Set(cards.filter(c => c.status === "live").map(c => c.family));
  const priorYears = new Map<string, number[]>();
  const poolSeeds = new Set(cards.filter(c => c.status !== "live" && c.event_start
      && Date.parse((c.event_end ?? c.registration_close ?? c.event_start) + "T23:59:59Z") < now)
    .sort((a, b) => (b.event_end ?? b.event_start!).localeCompare(a.event_end ?? a.event_start!))
    .slice(0, 12).map(c => `${c.family}|${c.year}`));
  for (const family of families) {
    const years = cards.filter(c => c.family === family && c.status !== "live")
      .map(c => c.year).sort((a, b) => b - a);
    priorYears.set(family, [...new Set(years)].slice(0, 2));
  }
  for (const card of cards) {
    if (!card.event_start) continue;
    const closed = Date.parse((card.event_end ?? card.registration_close ?? card.event_start) + "T23:59:59Z");
    const recent = closed <= now && now - closed < 90 * DAY;
    if (card.status !== "live" && !recent && !poolSeeds.has(`${card.family}|${card.year}`)
        && !(families.has(card.family) && priorYears.get(card.family)?.includes(card.year))) continue;
    let previous: Awaited<ReturnType<typeof readSnapshot>> = null;
    try { previous = await readSnapshot(env.FINANCE_KV, card.family, card.year); } catch { /* Recollect this damaged record; other events remain independent. */ }
    const attemptRaw = await env.FINANCE_KV.get(`event_status:${encodeURIComponent(card.family)}:${card.year}`);
    let lastAttempt: { attempted_at?: string; ok?: boolean; reason?: string; resume?: boolean } = {};
    try { if (attemptRaw) lastAttempt = JSON.parse(attemptRaw); } catch { /* Rebuild malformed status from source. */ }
    // One failed attempt per UTC day prevents an unmapped event monopolizing every batch.
    const repairedCalendar = lastAttempt.reason === "event_calendar_missing" && calendarDate(card.event_start)
      && (card.registration_close == null || calendarDate(card.registration_close));
    if (lastAttempt.ok === false && !lastAttempt.resume && !repairedCalendar
        && Date.parse(lastAttempt.attempted_at ?? "") >= midnight) continue;
    const due = card.status === "live" || recent ? midnight : now - 7 * DAY;
    if (!previous || lastAttempt.ok === false || Date.parse(previous.source_as_of) < due
        || Date.parse(card.count_observed_at ?? "") > Date.parse(previous.source_as_of)) {
      needed.push({ card, previous, priority: card.status === "live" ? 0 : recent ? 1 : 2, attempted: lastAttempt.attempted_at ?? "" });
    }
  }
  const byAge = (a: typeof needed[number], b: typeof needed[number]) => (a.previous?.source_as_of ?? "").localeCompare(b.previous?.source_as_of ?? "");
  const byRotation = (a: typeof needed[number], b: typeof needed[number]) => a.attempted.localeCompare(b.attempted) || byAge(a, b);
  needed.sort((a, b) => a.priority - b.priority || byRotation(a, b) || b.card.year - a.card.year || a.card.family.localeCompare(b.card.family));
  let collected = 0;
  let failed = 0;
  const calibration = needed.filter(item => item.priority > 0).sort(byRotation)[0];
  // Alternate first access across nightly batches. A costly successful report
  // must not starve either live events or historical calibration indefinitely.
  const other = needed.filter(item => item !== calibration).slice(0, 5);
  const calibrationFirst = new Date(now).getUTCHours() % 2 === 0;
  const batch = calibration ? calibrationFirst ? [calibration, ...other] : [...other, calibration] : needed.slice(0, 6);
  for (const { card, previous } of batch) {
    // Leave unstarted work due for the next batch, rather than marking it failed.
    if (client.remainingRequests < 4) break;
    const statusKey = `event_status:${encodeURIComponent(card.family)}:${card.year}`;
    const acquisition = new OrderAcquisition(env.FINANCE_KV, `${card.family}|${card.year}`, Date.now, previous?.source_as_of);
    try {
      const tournamentId = matchTournament(card, options);
      const filters = client.filters(tournamentId);
      const before = await parseSummary(await client.request("ajax_get_txn_total.php", filters));
      const rows = await client.playerRows(tournamentId);
      await acquisition.prefetch(rows.map(invoiceCacheKey));
      const after = await parseSummary(await client.request("ajax_get_txn_total.php", filters));
      if (JSON.stringify(before) !== JSON.stringify(after)) throw new Error("source_changed_during_read");
      const calendarCard = { ...card, registration_close: card.registration_close
        ?? (card.status !== "live" ? card.event_end ?? card.event_start : null) };
      const sourceAsOf = new Date(now + Math.max(0, Date.now() - wallStartedAt)).toISOString();
      const snapshot = await buildReceiptSnapshot(calendarCard, tournamentId, rows, after, sourceAsOf,
        (transaction, expected) => acquireCartRows(client, acquisition, transaction, expected),
        async () => parsePublicRegistrations(await client.publicEntryList(card.family, card.year)));
      validateSnapshot(snapshot);
      const stored = { ...snapshot, previous_net_cents: previous?.summary.net_cents ?? null,
        previous_as_of: previous?.source_as_of ?? null, projection: previous?.projection };
      if (card.status !== "live") await rememberHistory(env.FINANCE_KV, snapshot);
      const history = await readCalibration(env.FINANCE_KV, card.family);
      const projection = await receiptForecast(card, stored, history, Date.parse(sourceAsOf));
      if (!projection.missing) stored.projection = projection;
      await env.FINANCE_KV.put(snapshotKey(card.family, card.year), JSON.stringify(stored));
      await acquisition.committed();
      await env.FINANCE_KV.put(statusKey, JSON.stringify({ attempted_at: attemptedAt, ok: true, reason: null }));
      collected++;
    } catch (error) {
      await env.FINANCE_KV.put(statusKey, JSON.stringify({ attempted_at: attemptedAt, ok: false, reason: safeFailure(error),
        resume: safeFailure(error) === "source_request_limit" && acquisition.progressed > 0 }));
      failed++;
      if (safeFailure(error) === "source_request_limit") break;
    }
  }
  await env.FINANCE_KV.put("collector:status", JSON.stringify({ attempted_at: attemptedAt, ok: true, reason: null }));
  return { collected, failed };
}
