// Native test harness; neither production Worker references this module.
import { resolveTournament } from "../src/finance/source-edition";
import { ChessActionClient } from "../src/finance/client";
import financeWorker from "../src/finance/collector";
import { collectRegistrations } from "../src/finance/registration-collect";
import { registrationKey, registrationRecords, registrationFeedRecords } from "../src/finance/registration-store";
import { receiptValues } from "../src/finance/store";
import { cohortHash, sha256, snapshotKey } from "../src/finance/types";
import type { RegistrationCard } from "../src/finance/registrations";
import type { ReceiptCard, ReceiptSnapshot } from "../src/finance/types";

export async function registrationRuntime(request: Request): Promise<Response | null> {
  const path = new URL(request.url).pathname;
  if (!path.startsWith("/registration-")) return null;
  if (path === "/registration-edition") {
    const body = await request.json() as { card: RegistrationCard; options: Array<{ id: string; title: string }>; html: string };
    let reads = 0;
    try {
      const id = await resolveTournament(body.card, body.options, async () => { reads++; return body.html; });
      return Response.json({ id, reads });
    } catch (error) { return Response.json({ error: error instanceof Error ? error.message : "failed", reads }); }
  }
  const store = new Map<string, string>();
  let puts = 0;
  const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
    put: async (key: string, value: string) => { puts++; store.set(key, value); } } as unknown as KVNamespace;
  if (path === "/registration-null-timestamps") {
    const card: RegistrationCard = { family: "Example Open", year: 2026, status: "live", event_start: "2026-11-14" };
    const makeClient = (mode: "valid" | "missing" | "overflow") => {
      const client = new ChessActionClient();
      client.resume = async () => "<select id='tournments'><option value='123'>2026 Example Open</option></select>";
      client.request = async (_path, fields) => {
        const total = fields!.status === "active" ? (mode === "overflow" ? 2001 : 1) : 0;
        const start = Number(fields!.start), length = Number(fields!.length);
        const rows = Array.from({ length: Math.min(length, Math.max(0, total - start)) }, (_, i) => {
          const date = new Date(Date.parse("2026-11-01T12:00:00Z") - (start + i) * 86_400_000).toISOString().slice(0, 19).replace("T", " ");
          return { eventId: String(start + i + 1), tourid: "123", createdAt: mode === "missing" ? null
            : `<span title="${date} UTC">${date}<br />(GMT+00:00)</span>` };
        });
        return JSON.stringify({ aaData: rows, iTotalRecords: total, iTotalDisplayRecords: total });
      };
      return client;
    };
    const now = Date.parse("2026-11-10T00:40:00Z");
    await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, [card], now, makeClient("valid"));
    const previous = JSON.parse(store.get(registrationKey(card))!).data;
    const result = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, [card], now + 2 * 86_400_000, makeClient("missing"));
    const current = JSON.parse(store.get(registrationKey(card))!);
    const validation = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, [card], now + 4 * 86_400_000, makeClient("overflow"));
    const afterValidation = JSON.parse(store.get(registrationKey(card))!);
    return Response.json({ result, previous, current, validation, afterValidation });
  }
  if (path === "/registration-retry") {
    const cards: RegistrationCard[] = [
      { family: "A Costly Open", year: 2026, status: "complete", event_start: "2026-11-01" },
      { family: "B Ordinary Open", year: 2026, status: "live", event_start: "2026-11-14" },
    ];
    const makeClient = () => {
      let redirect = true;
      return new ChessActionClient(async (url, init) => {
        if (new URL(url).pathname === "/admin/search.php") return new Response("Continental Chess Association<select id='tournments'><option value='1'>2026 A Costly Open</option><option value='2'>2026 B Ordinary Open</option></select>");
        if (redirect) { redirect = false; return new Response(null, { status: 307, headers: { Location: url } }); }
        redirect = true;
        const fields = new URLSearchParams(init!.body as string);
        const active = fields.get("status") === "active";
        const total = active ? 5001 : 4999;
        const start = Number(fields.get("start")), length = Number(fields.get("length"));
        return Response.json({ iTotalRecords: total, iTotalDisplayRecords: total,
          aaData: Array.from({ length: Math.min(length, total - start) }, (_, i) => ({
            eventId: String((active ? 0 : 5001) + start + i + 1), tourid: fields.get("tournment"),
            createdAt: '<span title="2026-11-01 12:00:00 UTC">2026-11-01 12:00:00<br />(GMT+00:00)</span>',
          })) });
      });
    };
    const now = Date.parse("2026-11-10T00:40:00Z");
    const first = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, cards, now, makeClient());
    const retry = JSON.parse(store.get(registrationKey(cards[1]))!).retry;
    const second = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, cards, now + 3_600_000, makeClient());
    const records = await registrationRecords(kv, cards, now + 3_600_000);
    return Response.json({ first, retry, second, totals: records.map(r => r.data?.total), puts });
  }
  if (path === "/registration-failure-isolation") {
    // Keep its paid-history bucket inside the fixture's forecast horizon.
    const now = Date.parse("2026-11-10T02:40:00Z");
    const id = await sha256("synthetic-player");
    const card: ReceiptCard = { family: "Example Open", year: 2026, status: "live", current_count: 1, point_estimate: 2,
      event_start: "2026-11-14", regular_fee: 10, count_observed_at: new Date(now - 3_600_000).toISOString(), count_cohort_hash: await cohortHash([id]) };
    const snapshot: ReceiptSnapshot = { schema: 1, family: card.family, year: 2026, tournament_id: "123",
      source_as_of: new Date(now - 1_800_000).toISOString(), event_start: "2026-11-14", registration_close: "2026-11-15", regular_fee_cents: 1000,
      registration_count: 1, cohort: [{ id, paid_at: new Date(now - 86_400_000).toISOString() }],
      summary: { entry_cents: 1000, membership_cents: 0, contribution_cents: 0, other_cents: 0, refunded_cents: 0, net_cents: 1000 },
      buckets: [{ days_before: 2, registrations: 1, entry_cents: 1000, membership_cents: 0, contribution_cents: 0, other_cents: 0 }],
      previous_net_cents: null, previous_as_of: null };
    store.set(snapshotKey(card.family, card.year), JSON.stringify(snapshot));
    store.set(`history:${encodeURIComponent(card.family)}`, JSON.stringify([{ ...snapshot, year: 2025, registration_close: "2025-11-15" }]));
    const aggregate = { version: 1, family: card.family, year: card.year, tournament_id: "123", source_as_of: snapshot.source_as_of,
      active: 1, withdrawn: 0, total: 1, ts_count: 1, first_reg: "2026-11-01 12:00:00", last_reg: "2026-11-01 12:00:00",
      daily: [{ T: 0, daily_regs: 1 }], calendar_daily: [{ date: "2026-11-01", daily_regs: 1 }] };
    store.set(registrationKey(card), JSON.stringify({ attempted_at: snapshot.source_as_of, ok: true, reason: null, data: aggregate }));
    const before = await receiptValues(kv, [card], now);
    let fail = true;
    const storage = new Proxy(kv, { get(target, key) {
      if (key === "put") return async (k: string, v: string) => {
        if (fail && k === "registration_collector:status") { fail = false; puts++; throw new Error("synthetic_write_failure"); }
        return target.put(k, v);
      };
      return Reflect.get(target, key, target);
    }});
    let rejected = false;
    try { await financeWorker.scheduled({ cron: "0,20,40 * * * *", scheduledTime: Date.parse("2026-11-10T02:40:00Z") } as ScheduledController, { FINANCE_KV: storage }); }
    catch (error) { if (!(error instanceof Error) || error.message !== "registration_collection_failed") throw error; rejected = true; }
    return Response.json({ before, after: await receiptValues(kv, [card], now), rejected,
      training_feed: await registrationFeedRecords(kv, [card], Date.now()),
      financial_status_written: store.has("collector:status"), training_status_written: store.has("registration_collector:status"), puts });
  }
  return new Response(null, { status: 404 });
}
