// Local runtime harness only; neither production configuration references it.
import { ChessActionClient } from "../src/finance/client";
import { parseSummary, tournamentOptions } from "../src/finance/html";
import financeWorker from "../src/finance/collector";
import { collectBatch } from "../src/finance/collect";
import { invoiceContainsWholeOrder } from "../src/finance/invoice";
import { parsePublicRegistrations } from "../src/finance/public-cohort";
import type { ReceiptCard } from "../src/finance/types";

const syntheticInvoice = (event: string) => `<html><head></head><body><div id="invoicecontents"><div class="invoicetname">Tournamen Name: ${event}</div><div class="invoicekey">Player's Name: Synthetic</div><div class="invoicekey">Section: </div><div class="invoicevaluesub">Sub Total</div><div class="invoicevalueextend">US $10.00</div><div class="invoicevaluesub">PayPal Contribution</div><div class="invoicevalueextend">US $0.00</div><div class="invoicevaluesub">Grand Total</div><div class="invoicevalueextend">US $10.00</div><div class="invoicefotter">Footer</div></div></body></html>`;

export default {
  async fetch(request: Request): Promise<Response> {
    if (new URL(request.url).pathname === "/session-missing") {
      const store = new Map<string, string>();
      const kv = { put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
      let rejected = false;
      try {
        await financeWorker.scheduled({ cron: "*/10 0-1,9-23 * * *" } as ScheduledController, { FINANCE_KV: kv });
      } catch (error) {
        if (!(error instanceof Error) || error.message !== "finance_session_refresh_failed") throw error;
        rejected = true;
      }
      return Response.json({ rejected, session: JSON.parse(store.get("session:status")!), financial_status_written: store.has("collector:status") });
    }
    if (new URL(request.url).pathname === "/scheduled") {
      const store = new Map<string, string>();
      const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
        put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
      await financeWorker.scheduled({} as ScheduledController, { FINANCE_KV: kv });
      return Response.json(JSON.parse(store.get("collector:status")!));
    }
    if (new URL(request.url).pathname === "/default-fetch") {
      try {
        await new ChessActionClient().resume("session=synthetic");
        return Response.json({ ok: true });
      } catch (error) {
        return Response.json({ error: error instanceof Error ? error.message : "failed" }, { status: 422 });
      }
    }
    if (new URL(request.url).pathname === "/default-public-fetch") {
      try {
        await new ChessActionClient().publicEntryList("Los Angeles Open", 2026);
        return Response.json({ ok: true });
      } catch (error) {
        return Response.json({ error: error instanceof Error ? error.message : "failed" }, { status: 422 });
      }
    }
    if (new URL(request.url).pathname === "/repair") {
      const store = new Map<string, string>();
      const corrupt = new URL(request.url).searchParams.has("corrupt");
      if (corrupt) store.set("history:pooled", "invalid JSON");
      let failHistory = !corrupt;
      const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
        put: async (key: string, value: string) => {
          if (key === "history:pooled" && failHistory) { failHistory = false; throw new Error("synthetic_storage_failure"); }
          store.set(key, value);
        } } as unknown as KVNamespace;
      const client = () => {
        const source = new ChessActionClient();
        source.resume = async () => "<select id='tournments'><option value='123'>2026 Example Open</option></select>";
        source.request = async () => `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>10.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>10.00</td></tr></tbody></table>`;
        source.invoice = async () => syntheticInvoice("2026 Example Open");
        source.playerRows = async () => [{ order_id: "1", player_id: "1", paypal_trans_id: "synthetic", tournament: "2026 Example Open",
          status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "",
          order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }];
        return source;
      };
      const cards: ReceiptCard[] = [{ family: "Example Open", year: 2026, status: "complete",
        current_count: 1, event_start: "2026-11-01", event_end: "2026-11-02", regular_fee: 10 }];
      const first = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards,
        Date.parse("2026-11-09T02:30:00Z"), client());
      const freshAfterFailure = store.has("receipts:Example%20Open:2026");
      const second = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards,
        Date.parse("2026-11-10T02:30:00Z"), client());
      return Response.json({ first, freshAfterFailure, second,
        historyPresent: store.has("history:pooled"), snapshotPresent: store.has("receipts:Example%20Open:2026") });
    }
    if (new URL(request.url).pathname === "/budget-priority") {
      const store = new Map<string, string>();
      const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
        put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
      const source = new ChessActionClient();
      source.resume = async () => "<select id='tournments'><option value='1'>2026 Live Open</option><option value='2'>2026 Finished Open</option></select>";
      const attempted: string[] = [];
      source.request = async (_path, filters) => { attempted.push(filters!.tname); throw new Error("source_request_limit"); };
      await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, [
        { family: "Live Open", year: 2026, status: "live", current_count: 1, event_start: "2026-11-14" },
        { family: "Finished Open", year: 2026, status: "complete", current_count: 1, event_start: "2026-11-01" },
      ], Date.parse("2026-11-09T02:30:00Z"), source);
      return Response.json({ attempted });
    }
    if (new URL(request.url).pathname === "/costly-calibration") {
      const store = new Map<string, string>();
      const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
        put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
      const attempted: string[] = [];
      const client = () => {
        const source = new ChessActionClient();
        let remaining = 42;
        Object.defineProperty(source, "remainingRequests", { get: () => remaining });
        source.resume = async () => "<select id='tournments'><option value='1'>2026 Live Open</option><option value='2'>2026 Finished Open</option><option value='3'>2026 Another Finished Open</option></select>";
        source.request = async (_path, filters) => {
          if (remaining === 42) attempted.push(filters!.tname);
          remaining = 3;
          return `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>10.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>10.00</td></tr></tbody></table>`;
        };
        let selected = "";
        source.invoice = async () => syntheticInvoice(selected === "1" ? "2026 Live Open" : selected === "2" ? "2026 Finished Open" : "2026 Another Finished Open");
        source.playerRows = async id => { if (id !== "All") selected = id; return [{ order_id: "1", player_id: "1", paypal_trans_id: "synthetic", tournament: selected === "1" ? "2026 Live Open" : selected === "2" ? "2026 Finished Open" : "2026 Another Finished Open",
          status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "",
          order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }]; };
        return source;
      };
      const cards: ReceiptCard[] = [
        { family: "Live Open", year: 2026, status: "live", current_count: 1, event_start: "2026-11-14", registration_close: "2026-11-15", regular_fee: 10 },
        { family: "Finished Open", year: 2026, status: "complete", current_count: 1, event_start: "2026-11-01", regular_fee: 10 },
        { family: "Another Finished Open", year: 2026, status: "complete", current_count: 1, event_start: "2026-11-01", regular_fee: 10 },
      ];
      const batches = [];
      for (const hour of [2, 3]) batches.push(await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards,
        Date.parse(`2026-11-09T0${hour}:30:00Z`), client()));
      return Response.json({ attempted, batches });
    }
    if (new URL(request.url).pathname === "/scheduler") {
      const store = new Map<string, string>();
      const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
        put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
      const cards: ReceiptCard[] = Array.from({ length: 12 }, (_, i) => ({
        family: `Example ${i}`, year: 2026, status: "live", current_count: 1, event_start: "2026-11-14",
      }));
      cards.push({ family: "Finished Only", year: 2026, status: "complete", current_count: 1, event_start: "2026-11-01" });
      const makeClient = () => {
        const client = new ChessActionClient();
        client.resume = async () => "<select id='tournments'><option value='1'>2026 Unrelated Open</option></select>";
        return client;
      };
      for (let hour = 2; hour < 5; hour++) await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards,
        Date.parse(`2026-11-09T0${hour}:30:00Z`), makeClient());
      return Response.json({ attempted: [...store.keys()].filter(key => key.startsWith("event_status:")).length,
        finished_attempted: store.has("event_status:Finished%20Only:2026") });
    }
    if (new URL(request.url).pathname === "/http-is-private") {
      return Response.json({ status: (await financeWorker.fetch()).status });
    }
    const body = await request.json() as { html: string; expected?: Record<string, unknown>[]; replies?: Array<{ text: string; status?: number; location?: string; cookie?: string }> };
    try {
      if (new URL(request.url).pathname === "/invoice-proof") return Response.json({ whole: await invoiceContainsWholeOrder(body.html, body.expected ?? []) });
      if (new URL(request.url).pathname === "/summary") return Response.json(await parseSummary(body.html));
      if (new URL(request.url).pathname === "/options") return Response.json(await tournamentOptions(body.html));
      if (new URL(request.url).pathname === "/public-cohort") return Response.json(await parsePublicRegistrations(body.html));
      const calls: Array<{ path: string; method?: string; cookie: boolean }> = [];
      const replies = [...(body.replies ?? [])];
      const client = new ChessActionClient(async (url, init) => {
        calls.push({ path: new URL(url).pathname, method: init?.method, cookie: new Headers(init?.headers).has("Cookie") });
        const reply = replies.shift();
        if (!reply) throw new Error("fixture_exhausted");
        const headers = new Headers();
        if (reply.location) headers.set("Location", reply.location);
        if (reply.cookie) headers.append("Set-Cookie", reply.cookie);
        return new Response(reply.text, { status: reply.status ?? 200, headers });
      });
      if (new URL(request.url).pathname === "/pages") {
        const rows = await client.playerRows("123");
        return Response.json({ count: rows.length, calls });
      }
      if (new URL(request.url).pathname === "/resume") {
        await client.resume("session=synthetic");
        return Response.json({ ok: true, calls });
      }
      if (new URL(request.url).pathname === "/public-fetch") {
        await client.resume("session=synthetic");
        await client.publicEntryList("Los Angeles Open", 2026);
        return Response.json({ calls });
      }
      await client.login("synthetic-user", "synthetic-password");
      return Response.json({ ok: true, calls });
    } catch (error) {
      return Response.json({ error: error instanceof Error ? error.message : "failed" }, { status: 422 });
    }
  },
};
