import { collectRegistrations } from "../src/finance/registration-collect";
import { collectBatch } from "../src/finance/collect";
import { ChessActionClient } from "../src/finance/client";
import { refreshSession } from "../src/finance/session";
import type { ReceiptCard } from "../src/finance/types";
import { FinanceWriteBudget } from "../src/finance/write-budget";

export interface DailySlot { minute: number; heartbeat: boolean }

/** Run the actual collector/checkpoint/publication paths against counted KV. */
export async function quotaDays(slots: DailySlot[], invoice: (event: string) => string) {
  const store = new Map<string, string>();
  const realNow = Date.now;
  let tick = Date.parse("2026-11-09T00:00:00Z");
  let writes = 0;
  const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
    put: async (key: string, value: string) => { writes++; store.set(key, value); } } as unknown as KVNamespace;
  const cards: ReceiptCard[] = Array.from({ length: 36 }, (_, i) => ({ family: `Quota ${i} Open`, year: 2026,
    status: "live", current_count: 32, point_estimate: 40, regular_fee: 10, event_start: "2026-11-14" }));
  const options = `<select id='tournments'>${cards.map((card, i) => `<option value='${i + 1}'>2026 ${card.family}</option>`).join("")}</select>`;
  const client = () => {
    const source = new ChessActionClient();
    let remaining = 42; let selected = 0;
    const use = () => { if (--remaining < 0) throw new Error("source_request_limit"); };
    Object.defineProperty(source, "remainingRequests", { get: () => Math.max(0, remaining) });
    source.resume = async () => { use(); return options; };
    source.request = async (path, fields) => {
      use();
      if (path === "ajaxRegistrationDataTable.php") {
        const rows = fields!.status === "active" ? Array.from({ length: 32 }, (_, i) => ({
          tourid: fields!.tournment, eventId: String(i + 1),
          createdAt: '<span title="2026-11-01 12:00:00 UTC">2026-11-01 12:00:00<br />(GMT+00:00)</span>',
        })) : [];
        return JSON.stringify({ iTotalRecords: rows.length, iTotalDisplayRecords: rows.length,
          aaData: rows.slice(0, Number(fields!.length)) });
      }
      return `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>320.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>320.00</td></tr></tbody></table>`;
    };
    source.playerRows = async id => {
      use(); selected = Number(id) - 1;
      return Array.from({ length: 32 }, (_, i) => ({ order_id: String((selected + 1) * 1000 + i),
        player_id: String(i + 1), paypal_trans_id: "synthetic", tournament: `2026 ${cards[selected].family}`,
        status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "",
        order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }));
    };
    source.invoice = async () => { use(); return invoice(`2026 ${cards[selected].family}`); };
    return source;
  };
  const days = [];
  try {
    Date.now = () => tick;
    for (let day = 0; day < 2; day++) {
      const initial = writes;
      let maximumBatch = 0; let maximumHeartbeat = 0; let completed = 0; let trainingCompleted = 0; let trainingSlots = 0; let moneySlots = 0;
      for (const slot of slots) {
        tick = Date.parse("2026-11-09T00:00:00Z") + day * 86_400_000 + slot.minute * 60_000;
        const before = writes;
        if (slot.heartbeat) {
          const health = new ChessActionClient(); health.resume = async () => options;
          await refreshSession({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, tick, health);
          maximumHeartbeat = Math.max(maximumHeartbeat, writes - before);
        } else if (slot.minute % 60 === 40) {
          trainingSlots++;
          const result = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, cards, tick, client());
          trainingCompleted += result.collected;
          maximumBatch = Math.max(maximumBatch, writes - before);
        } else {
          moneySlots++;
          const result = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, cards, tick, client());
          completed += result.collected;
          maximumBatch = Math.max(maximumBatch, writes - before);
        }
      }
      const snapshots = [...store.entries()].filter(([key]) => key.startsWith("receipts:")).map(([, raw]) => JSON.parse(raw));
      days.push({ writes: writes - initial, maximumBatch, maximumHeartbeat, completed, trainingCompleted, trainingSlots, moneySlots,
        trainingSnapshots: [...store.keys()].filter(key => key.startsWith("registrations:")).length,
        snapshots: snapshots.length, conserved: snapshots.every(value => value.summary.net_cents === 32000),
        checkpointWritesArePerEvent: [...store.keys()].filter(key => key.startsWith("order_checkpoint:")).length === 36 });
    }
  } finally { Date.now = realNow; }
  return { days };
}

export async function quotaFaults(invoice: (event: string) => string) {
  const results = [];
  const realNow = Date.now;
  const tick = Date.parse("2026-11-09T02:30:00Z");
  try {
    Date.now = () => tick;
    const failures = [0];
    for (const failAt of failures) {
      const store = new Map<string, string>(); const trace: string[] = [];
      let failureReached = false;
      let unpersistedResume = false; let publicationWithoutFence = false;
      const kv = { get: async (key: string) => store.get(key) ?? null,
        put: async (key: string, value: string) => {
          trace.push(key.split(":")[0]);
          if (trace.length === failAt || failAt === -1) { failureReached = true; throw Error("synthetic_storage_failure"); }
          if (key.startsWith("receipts:") || key.startsWith("history:")) {
            const snapshot = key.startsWith("history:") ? JSON.parse(value).at(-1) : JSON.parse(value);
            const checkpoint = store.get(`order_checkpoint:2:${encodeURIComponent(snapshot.family + "|2026")}`);
            const parsed = checkpoint ? JSON.parse(checkpoint) : null;
            const marker = parsed ? store.get(`order_retired:2:${encodeURIComponent(snapshot.family + "|2026")}:${parsed.generation}`) : null;
            if (!parsed?.retired_at || marker !== "complete") publicationWithoutFence = true;
          }
          if (key.startsWith("event_status:") && JSON.parse(value).resume) {
            const family = decodeURIComponent(key.split(":")[1]);
            if (!store.has(`order_checkpoint:2:${encodeURIComponent(family + "|2026")}`)) unpersistedResume = true;
          }
          store.set(key, value);
        } } as unknown as KVNamespace;
      const source = new ChessActionClient(); let selected = "Finished Open";
      source.resume = async () => "<select id='tournments'><option value='1'>2026 Finished Open</option><option value='2'>2026 Live Open</option></select>";
      source.request = async () => `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>10.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>10.00</td></tr></tbody></table>`;
      source.playerRows = async id => {
        selected = id === "1" ? "Finished Open" : "Live Open";
        return [{ order_id: id, player_id: "1", paypal_trans_id: "synthetic", tournament: `2026 ${selected}`,
          status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "",
          order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }];
      };
      source.invoice = async () => invoice(`2026 ${selected}`);
      const writes = new FinanceWriteBudget(kv);
      const cards = [{ family: "Finished Open", year: 2026, status: "complete", current_count: 1, event_start: "2026-11-01", event_end: "2026-11-02", regular_fee: 10 },
        { family: "Live Open", year: 2026, status: "live", current_count: 1, event_start: "2026-11-14", regular_fee: 10 }];
      try { await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards, tick, source, writes); }
      catch {
        try { await writes.kv.put("collector:status", JSON.stringify({ attempted_at: new Date(tick).toISOString(), ok: false, reason: "collection_failed" })); }
        catch { /* The receipt includes this refused diagnostic attempt. */ }
      }
      results.push({ failAt, failureReached, writes: trace.length, trace, unpersistedResume, publicationWithoutFence });
      if (failAt === 0) failures.push(...Array.from({ length: trace.length }, (_, i) => i + 1), -1);
    }
  } finally { Date.now = realNow; }
  return results;
}

export async function zeroProgress(invoice: (event: string) => string) {
  const store = new Map<string, string>();
  const kv = { get: async (key: string) => store.get(key) ?? null,
    put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
  const client = () => {
    const source = new ChessActionClient();
    source.resume = async () => "<select id='tournments'><option value='1'>2026 Example Open</option></select>";
    source.request = async () => `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>20.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>20.00</td></tr></tbody></table>`;
    source.playerRows = async () => ["1", "2"].map(id => ({ order_id: id, player_id: id, paypal_trans_id: "synthetic",
      tournament: "2026 Example Open", status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "",
      order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }));
    source.invoice = async id => { if (id === "2") throw Error("source_request_limit"); return invoice("2026 Example Open"); };
    return source;
  };
  const cards = [{ family: "Example Open", year: 2026, status: "live", current_count: 2, event_start: "2026-11-14", regular_fee: 10 }];
  const states = [];
  for (let i = 0; i < 3; i++) {
    const result = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards, Date.now(), client());
    states.push({ result, resume: JSON.parse(store.get("event_status:Example%20Open:2026")!).resume });
  }
  return states;
}

/** An ordinary shared cart admitted after an expensive preceding event must retry. */
export async function leftoverBudget(invoice: (event: string) => string) {
  const store = new Map<string, string>();
  const kv = { get: async (key: string) => store.get(key) ?? null,
    put: async (key: string, value: string) => { store.set(key, value); } } as unknown as KVNamespace;
  const row = (id: string, event: string, amount = "10.00") => ({ order_id: id, player_id: id,
    paypal_trans_id: "synthetic", tournament: `2026 ${event}`, status: "Approved", section_amount: amount,
    membership_amount: "0.00", is_deleted: "", order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" });
  const second = row("100", "B Open"); const foreign = row("100", "Other Open", "0.00");
  const client = () => {
    const source = new ChessActionClient(); let remaining = 42;
    const use = () => { if (--remaining < 0) throw Error("source_request_limit"); };
    Object.defineProperty(source, "remainingRequests", { get: () => Math.max(0, remaining) });
    source.resume = async () => { use(); return "<select id='tournments'><option value='1'>2026 A Open</option><option value='2'>2026 B Open</option></select>"; };
    source.request = async (_path, filters) => { use(); const amount = filters!.tname === "1" ? "340.00" : "10.00";
      return `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>${amount}</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>${amount}</td></tr></tbody></table>`; };
    source.playerRows = async id => { use(); return id === "All" ? [second, foreign] : id === "2" ? [second]
      : Array.from({ length: 34 }, (_, i) => row(String(i + 1), "A Open")); };
    source.invoice = async id => { use(); if (id !== "100") return invoice("2026 A Open");
      const extra = `<div class="invoicetname">Tournamen Name: 2026 Other Open</div><div class="invoicekey">Player's Name: Synthetic</div><div class="invoicekey">Section: </div><div class="invoicevaluesub">Sub Total</div><div class="invoicevalueextend">US $0.00</div>`;
      return invoice("2026 B Open").replace('<div class="invoicevaluesub">PayPal Contribution</div>', extra + '<div class="invoicevaluesub">PayPal Contribution</div>'); };
    return source;
  };
  const cards = [{ family: "A Open", year: 2026, status: "live", current_count: 34, event_start: "2026-11-14", regular_fee: 10 },
    { family: "B Open", year: 2026, status: "live", current_count: 1, event_start: "2026-11-14", regular_fee: 10 }];
  const now = Date.now(); const first = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards, now, client());
  const resume = JSON.parse(store.get("event_status:B%20Open:2026")!).resume;
  const secondRun = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" }, cards, now, client());
  return { first, resume, second: secondRun, net: JSON.parse(store.get("receipts:B%20Open:2026") ?? "null")?.summary.net_cents };
}

/** New proof persistence, including an older existing root, precedes resume:true. */
export async function resumePersistence(invoice: (event: string) => string) {
  const results = [];
  for (const failCheckpoint of [false, true]) {
    const store = new Map<string, string>(); let attempts = 0; let failing = false;
    const checkpointKey = "order_checkpoint:2:Example%20Open%7C2026";
    const kv = { get: async (key: string) => store.get(key) ?? null,
      put: async (key: string, value: string) => {
        if (key === checkpointKey) { attempts++; if (failing && failCheckpoint) throw Error("synthetic_storage_failure"); }
        store.set(key, value);
      } } as unknown as KVNamespace;
    const client = (stop: number) => {
      const source = new ChessActionClient();
      source.resume = async () => "<select id='tournments'><option value='1'>2026 Example Open</option></select>";
      source.request = async () => `<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>30.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>30.00</td></tr></tbody></table>`;
      source.playerRows = async () => ["1", "2", "3"].map(id => ({ order_id: id, player_id: id, paypal_trans_id: "synthetic", tournament: "2026 Example Open",
        status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "", order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }));
      source.invoice = async id => { if (Number(id) === stop) throw Error("source_request_limit"); return invoice("2026 Example Open"); };
      return source;
    };
    const cards = [{ family: "Example Open", year: 2026, status: "live", current_count: 3, event_start: "2026-11-14", regular_fee: 10 }];
    const env = { FINANCE_KV: kv, CHESS_ACTION_COOKIE: "synthetic" };
    await collectBatch(env, cards, Date.now(), client(2)); // Root has one proof.
    const before = store.get(checkpointKey)!; store.delete("event_status:Example%20Open:2026"); failing = true;
    let rejected = false;
    try { await collectBatch(env, cards, Date.now(), client(3)); } catch { rejected = true; }
    results.push({ failCheckpoint, rejected, attempts, beforeProofs: Object.keys(JSON.parse(before).orders).length,
      afterProofs: Object.keys(JSON.parse(store.get(checkpointKey)!).orders).length,
      resume: JSON.parse(store.get("event_status:Example%20Open:2026") ?? "null")?.resume ?? null });
  }
  return results;
}
