import { receiptForecast } from "./forecast";
import { snapshotKey, validateSnapshot } from "./types";
import type { ReceiptCard, ReceiptSnapshot, ReceiptValue } from "./types";

export interface StoredReceipt extends ReceiptSnapshot { projection?: ReceiptValue; source_policy_version?: number }
export interface CollectorStatus { attempted_at: string; ok: boolean; reason: string | null }

function sessionStatus(raw: string | null): CollectorStatus | null {
  if (raw === null) return null;
  const value = JSON.parse(raw) as Partial<CollectorStatus> | null;
  if (!value || typeof value !== "object" || typeof value.ok !== "boolean"
      || typeof value.attempted_at !== "string" || !Number.isFinite(Date.parse(value.attempted_at))
      || new Date(value.attempted_at).toISOString() !== value.attempted_at
      || (value.ok ? value.reason !== null : typeof value.reason !== "string" || !value.reason)) {
    throw new Error("invalid_session_status");
  }
  return value as CollectorStatus;
}

export const invalidHistory = (error: unknown) => error instanceof SyntaxError || error instanceof Error
  && ["invalid_history", "invalid_snapshot", "summary_mismatch", "duplicate_registration"].includes(error.message);

export async function readSnapshot(kv: KVNamespace, family: string, year: number, now = Date.now()): Promise<StoredReceipt | null> {
  const raw = await kv.get(snapshotKey(family, year));
  if (raw === null) return null;
  const snapshot: StoredReceipt = validateSnapshot(JSON.parse(raw));
  const p = snapshot.projection;
  if (p !== undefined && (!p || p.family !== snapshot.family || p.year !== snapshot.year
      || p.basis !== "chess_action_receipts" || p.coverage !== "chess_action"
      || p.missing !== null || p.stale !== false || !["family", "pooled"].includes(p.confidence ?? "")
      || ![p.actual_cents, p.future_cents, p.refund_reserve_cents].every(n => Number.isSafeInteger(n) && n! >= 0)
      || !Number.isFinite(p.value) || p.value !== (p.actual_cents! + p.future_cents! - p.refund_reserve_cents!) / 100
      || !Number.isFinite(Date.parse(p.source_as_of ?? "")) || !Number.isFinite(Date.parse(p.model_observed_at ?? ""))
      || Date.parse(p.model_observed_at!) > now + 60_000 || Date.parse(p.source_as_of!) > now + 60_000
      || Date.parse(p.source_as_of!) > Date.parse(snapshot.source_as_of)
      || p.last_day !== null && (!p.last_day || !Number.isFinite(p.last_day.value)
        || !Number.isSafeInteger(p.last_day.span) || p.last_day.span <= 0))) throw new Error("invalid_snapshot");
  return snapshot;
}

export async function readHistory(kv: KVNamespace, family: string): Promise<ReceiptSnapshot[]> {
  const raw = await kv.get(`history:${encodeURIComponent(family)}`);
  if (raw === null) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error("invalid_history");
  return parsed.map(validateSnapshot);
}

export async function readCalibration(kv: KVNamespace, family: string): Promise<ReceiptSnapshot[]> {
  const caches = await Promise.allSettled([readHistory(kv, family), readHistory(kv, "pooled")]);
  caches.forEach((cache, i) => {
    if (cache.status === "rejected") console.error(JSON.stringify({ event: "finance_calibration_cache_failed", cache: i ? "pooled" : "family" }));
  });
  if (caches.every(cache => cache.status === "rejected")) throw new Error("calibration_unavailable");
  const selected = new Map<string, ReceiptSnapshot>();
  for (const item of caches.flatMap(cache => cache.status === "fulfilled" ? cache.value : [])) {
    const key = `${item.family}|${item.year}`;
    if (!selected.has(key) || selected.get(key)!.source_as_of < item.source_as_of) selected.set(key, item);
  }
  return [...selected.values()];
}

export async function receiptValues(kv: KVNamespace, cards: ReceiptCard[], now = Date.now()): Promise<ReceiptValue[]> {
  const [statusRaw, sessionRaw] = await Promise.all([kv.get("collector:status"), kv.get("session:status")]);
  const status = statusRaw ? JSON.parse(statusRaw) as CollectorStatus : null;
  const session = sessionStatus(sessionRaw);
  return Promise.all(cards.filter(c => c.status === "live").map(async card => {
    let snapshot: StoredReceipt | null = null;
    try {
    snapshot = await readSnapshot(kv, card.family, card.year, now);
    // A withdrawn attendance forecast retires its cached money projection.
    // Preserve recorded receipts, but do not revive an unsupported estimate.
    if (!Number.isInteger(card.point_estimate) || card.point_estimate! < 0) {
      return receiptForecast(card, snapshot, [], now);
    }
    const history = await readCalibration(kv, card.family);
    let value = await receiptForecast(card, snapshot, history, now);
    const eventStatusRaw = await kv.get(`event_status:${encodeURIComponent(card.family)}:${card.year}`);
    const eventStatus = eventStatusRaw ? JSON.parse(eventStatusRaw) as CollectorStatus : null;
    if (eventStatus?.ok === false && eventStatus.attempted_at >= (value.source_as_of ?? "")) {
      value = { ...value, value: null, stale: true, missing: "collection_failed" };
    }
    if (status?.ok === false && status.attempted_at >= (value.source_as_of ?? "")) {
      value = { ...value, value: null, stale: true, missing: "collection_failed" };
    }
    if (session?.ok === false && session.attempted_at >= (value.source_as_of ?? "")) {
      value = { ...value, value: null, stale: true, missing: "collection_failed" };
    }
    // Only a previously validated projection is retained. Never synthesize a
    // replacement from current counts and public fee estimates after failure.
    if (value.missing && snapshot?.projection?.value !== null && snapshot?.projection?.value !== undefined) {
      return { ...snapshot.projection, stale: true, missing: value.missing };
    }
    return value;
    } catch {
      if (snapshot?.projection?.value !== null && snapshot?.projection?.value !== undefined) {
        return { ...snapshot.projection, stale: true, missing: "calibration_unavailable" };
      }
      const unavailable = await receiptForecast(card, null, [], now);
      return { ...unavailable, missing: "invalid_receipts", stale: true };
    }
  }));
}
