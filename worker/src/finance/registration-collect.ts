import { ChessActionClient } from "./client";
import type { FinanceEnv } from "./collect";
import { resolveTournament } from "./source-edition";
import { tournamentOptions } from "./html";
import { acquireRegistrations, validateRegistrations } from "./registrations";
import { registrationFailure, registrationKey, registrationRecords } from "./registration-store";
import type { RegistrationCard } from "./registrations";
import { FinanceWriteBudget } from "./write-budget";

// ScheduledController.cron contains the whole expression, so select the slot
// by scheduledTime, never by the late wall clock of an invocation.
export const isRegistrationTick = (scheduledTime: number) => new Date(scheduledTime).getUTCMinutes() === 40;
export function needsFinalCapture(card: RegistrationCard, sourceAsOf: string | undefined, now: number): boolean {
  const ready = Date.parse((card.event_end ?? card.event_start) + "T00:00:00Z") + 38 * 3_600_000;
  return card.status !== "live" && Number.isFinite(ready) && now >= ready
    && (!sourceAsOf || Date.parse(sourceAsOf) < ready);
}
export async function collectRegistrations(env: FinanceEnv, cards: RegistrationCard[], now: number,
  client = new ChessActionClient(), writes = new FinanceWriteBudget(env.FINANCE_KV)) {
  const startedAt = Date.now();
  const attemptedAt = new Date(now).toISOString();
  const statusKey = "registration_collector:status";
  if (!env.CHESS_ACTION_COOKIE) {
    await writes.kv.put(statusKey, JSON.stringify({ attempted_at: attemptedAt, ok: false, reason: "source_session_required" }));
    return { collected: 0, failed: 1 };
  }
  const options = await tournamentOptions(await client.resume(env.CHESS_ACTION_COOKIE));
  const freshRequests = client.remainingRequests;
  const records = await registrationRecords(writes.kv, cards, now);
  const midnight = attemptedAt.slice(0, 10);
  const byKey = new Map(cards.map(c => [registrationKey(c), c]));
  const due = records.filter(r => {
    if (!r.ok && !r.retry && r.attempted_at?.slice(0, 10) === midnight) return false;
    const card = byKey.get(registrationKey(r))!;
    const age = card.status === "live" ? 86_400_000 : 7 * 86_400_000;
    return needsFinalCapture(card, r.data?.source_as_of, now)
      || !r.data || !r.ok || Date.parse(r.data.source_as_of) < now - age;
  }).sort((a, b) => (a.attempted_at ?? "").localeCompare(b.attempted_at ?? "") || a.family.localeCompare(b.family) || b.year - a.year);
  // One backfill and two live reports per opportunity, filling unused places
  // from the other queue. Oldest attempt includes failures: no event monopolizes.
  const live = due.filter(r => byKey.get(registrationKey(r))!.status === "live");
  const history = due.filter(r => byKey.get(registrationKey(r))!.status !== "live");
  const batch = [...history.slice(0, 1), ...live.slice(0, 2)];
  for (const record of due) if (batch.length < 3 && !batch.includes(record)) batch.push(record);
  let collected = 0, failed = 0;
  for (const previous of batch) {
    if (client.remainingRequests < 5 || writes.remaining < 3) break;
    const leftover = client.remainingRequests < freshRequests;
    const card = byKey.get(registrationKey(previous))!;
    let data = previous.data, reason: string | null = null;
    try {
      let candidate = await acquireRegistrations(client, card, await resolveTournament(card, options, id => client.eventSettings(id)), new Date(now + Math.max(0, Date.now() - startedAt)).toISOString());
      candidate = { ...candidate, source_as_of: new Date(now + Math.max(0, Date.now() - startedAt)).toISOString() };
      validateRegistrations(candidate, card);
      data = candidate;
    } catch (error) { reason = registrationFailure(error); }
    // A storage failure propagates to the bounded outer handler; never retry
    // the same publication as an error status or claim resumable progress.
    await writes.kv.put(registrationKey(card), JSON.stringify({ attempted_at: attemptedAt, ok: reason === null, reason, data, retry: reason === "source_request_limit" && leftover }));
    if (reason === null) collected++; else failed++;
    if (reason === "source_request_limit") break;
  }
  await writes.kv.put(statusKey, JSON.stringify({ attempted_at: attemptedAt, ok: true, reason: null, collected, failed }));
  return { collected, failed };
}
