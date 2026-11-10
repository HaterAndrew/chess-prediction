import { validateRegistrations, type RegistrationAggregate } from "./registrations";
import type { RegistrationCard } from "./registrations";

export const registrationKey = (card: { family: string; year: number }) => `registrations:${encodeURIComponent(card.family)}:${card.year}`;
const REASONS = new Set(["source_session_required", "source_login_expired", "source_login_failed", "source_request_limit", "source_network_failed",
  "source_timeout", "source_http_failed", "source_destination_refused", "source_incomplete", "source_too_many_rows", "source_changed_during_read",
  "registration_schema_changed", "registration_time_invalid", "registration_timestamps_missing", "registration_identity_invalid", "unmapped_tournament", "ambiguous_tournament", "incompatible_edition", "source_schema_changed",
  "registration_cache_invalid", "collection_failed"]);
export const registrationFailure = (error: unknown): string => error instanceof Error && REASONS.has(error.message) ? error.message : "collection_failed";
export interface RegistrationRecord {
  family: string;
  year: number;
  attempted_at: string | null;
  ok: boolean;
  reason: string | null;
  data: RegistrationAggregate | null;
  retry: boolean;
}
export function registrationTargets(cards: RegistrationCard[], now: number): RegistrationCard[] {
  const keys = new Set<string>();
  const targets = cards.filter(card => {
    if (!card || typeof card.family !== "string" || !card.family || card.family.length > 200 || !Number.isInteger(card.year)
        || card.year < Math.max(2026, new Date(now).getUTCFullYear() - 1) || card.year > new Date(now).getUTCFullYear() + 1 || !card.event_start) return false;
    const key = registrationKey(card);
    if (keys.has(key)) throw new Error("registration_cache_invalid");
    keys.add(key); return true;
  });
  if (targets.length > 200) throw new Error("registration_cache_invalid");
  return targets;
}
export async function registrationRecords(kv: KVNamespace, cards: RegistrationCard[], now = Date.now()): Promise<RegistrationRecord[]> {
  const targets = registrationTargets(cards, now);
  const records: RegistrationRecord[] = [];
  for (let i = 0; i < targets.length; i += 100) {
    const group = targets.slice(i, i + 100);
    const values = await kv.get(group.map(registrationKey), "text");
    for (const card of group) {
      const base = { family: card.family, year: card.year };
      try {
        const text = values.get(registrationKey(card));
        if (!text) { records.push({ ...base, attempted_at: null, ok: false, reason: "not_collected", data: null, retry: false }); continue; }
        if (text.length > 256_000) throw new Error("registration_cache_invalid");
        const x = JSON.parse(text);
        if (typeof x.ok !== "boolean" || typeof x.attempted_at !== "string" || !/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(x.attempted_at) || !Number.isFinite(Date.parse(x.attempted_at))
            || new Date(x.attempted_at).toISOString() !== x.attempted_at
            || Date.parse(x.attempted_at) > now + 300_000 || (x.reason !== null && !REASONS.has(x.reason))) throw new Error("registration_cache_invalid");
        const data = x.data === null ? null : validateRegistrations(x.data, card);
        if (data && Date.parse(data.source_as_of) > now + 300_000 || x.ok && !data || x.ok && x.reason !== null) throw new Error("registration_cache_invalid");
        // Do not forward arbitrary envelope/cache fields across the RPC boundary.
        records.push({ ...base, attempted_at: x.attempted_at, ok: x.ok, reason: x.reason, data, retry: x.retry === true && x.reason === "source_request_limit" });
      } catch {
        records.push({ ...base, attempted_at: null, ok: false, reason: "registration_cache_invalid", data: null, retry: false });
      }
    }
    if (new TextEncoder().encode(JSON.stringify(records)).byteLength > 6_000_000) throw new Error("registration_cache_invalid");
  }
  return records;
}


/** Serving health is independent of scheduling/backoff and never changes data. */
export async function registrationFeedRecords(kv: KVNamespace, cards: RegistrationCard[], now = Date.now()) {
  const records = await registrationRecords(kv, cards, now);
  const raw = await kv.get("registration_collector:status");
  if (raw === null) return records;
  let failure: { attempted_at: string; reason: string } | null = null;
  try {
    const status = JSON.parse(raw);
    if (!status || typeof status.ok !== "boolean" || typeof status.attempted_at !== "string"
        || !/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(status.attempted_at)
        || !Number.isFinite(Date.parse(status.attempted_at)) || new Date(status.attempted_at).toISOString() !== status.attempted_at
        || Date.parse(status.attempted_at) > now + 300_000
        || (status.ok ? status.reason !== null : !REASONS.has(status.reason))) throw new Error("registration_cache_invalid");
    if (!status.ok) failure = { attempted_at: status.attempted_at, reason: status.reason };
  } catch {
    return records.map(r => ({ ...r, ok: false, reason: "registration_cache_invalid" }));
  }
  return records.map(r => r.reason !== "registration_cache_invalid" && failure && (!r.data || Date.parse(failure.attempted_at) >= Date.parse(r.data.source_as_of))
      && (!r.attempted_at || Date.parse(failure.attempted_at) >= Date.parse(r.attempted_at))
    ? { ...r, ok: false, reason: failure.reason } : r);
}
