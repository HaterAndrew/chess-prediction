import { ChessActionClient } from "../src/finance/client";
import { collectBatch } from "../src/finance/collect";
import { cohortHash, sha256, snapshotKey } from "../src/finance/types";
import { receiptForecast } from "../src/finance/forecast";

/** Exercise the receipt collector's exact event/calendar and invoice boundary. */
export async function receiptEditionRuntime(request: Request, invoice: (event: string) => string): Promise<Response | null> {
  if (new URL(request.url).pathname !== "/receipt-edition") return null;
  const { wrongYear = false, foreignRow = false, empty = false, staleProfile = false, foreignLinks = false,
    wrongNativeEvent = false, changedNativeCount = false, limited = false } = await request.json() as {
    wrongYear?: boolean; foreignRow?: boolean; empty?: boolean; staleProfile?: boolean; foreignLinks?: boolean;
    wrongNativeEvent?: boolean; changedNativeCount?: boolean; limited?: boolean;
  };
  const family = "Saratoga Tournament Of-The-Ages Open";
  const now = Date.now();
  const card = { family, year: 2027, status: "live", current_count: empty ? 0 : 1, point_estimate: empty ? null : 2,
    event_start: "2027-02-26", registration_close: "2027-02-28", regular_fee: 10,
    count_observed_at: new Date(now).toISOString(), count_cohort_hash: await cohortHash(empty ? [] : [await sha256(staleProfile ? "101" : "1")]) };
  const store = new Map<string, string>();
  const key = `event_status:${encodeURIComponent(family)}:2027`;
  store.set(key, JSON.stringify({ attempted_at: new Date(now - 1000).toISOString(), ok: false,
    reason: "unmapped_tournament", source_policy_version: 2, resume: false }));
  let settingsReads = 0;
  let reportReads = 0;
  const requests: Array<{ path: string; method: string }> = [];
  const sourceCalls: number[] = [];
  const client = (limit = 42) => {
    const index = sourceCalls.push(0) - 1;
    return new ChessActionClient(async (raw, init) => {
    sourceCalls[index]++;
    const url = new URL(raw);
    requests.push({ path: url.pathname, method: init?.method ?? "GET" });
    if (url.pathname === "/admin/search.php") {
      return new Response(`<h1>Continental Chess Association</h1><select id="tournments"><option value="4912">${family}</option></select>`);
    }
    if (url.pathname === "/admin/add_edit_tour.php") {
      settingsReads++;
      if (init?.method !== "GET" || url.search !== "?tid=4912") throw new Error("unexpected_settings_request");
      return new Response(`<input name="tid" value="4912"><input name="tourid" value="4912"><input name="tname" value="${family}"><input name="startson" value="${wrongYear ? "2026" : "2027"}-02-26">`);
    }
    if (url.pathname === "/admin/ajax_get_txn_total.php") {
      const amount = empty ? "0.00" : "10.00";
      return new Response(`<table><thead><tr><th>Tournament fees ($) [Cart Discounts deducted]</th><th>Primary membership fees ($)</th><th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th></tr></thead><tbody><tr><td>${amount}</td><td>0.00</td><td>0.00</td><td>0.00</td><td>0.00</td><td>${amount}</td></tr></tbody></table>`);
    }
    if (url.pathname === "/admin/set_player_data_for_datatable.php") {
      reportReads++;
      const rows = empty ? [] : [{ order_id: "1", player_id: "1", paypal_trans_id: "synthetic", tournament: foreignRow ? "2026 " + family : family,
        section: "", status: "Approved", section_amount: "10.00", membership_amount: "0.00", is_deleted: "",
        order_value: "10.00", payment_date: "2026-11-01", payment_time: "12:00:00" }];
      if (staleProfile && rows[0]) Object.assign(rows[0], { uscf_id: "12345678", fide_id: "" });
      return Response.json({ recordsFiltered: rows.length, data: rows });
    }
    if (url.pathname.includes("/advlists/")) {
      const headers = ["Player's Name", "Player's Name", "FIDE ID", "FIDE Rating", "USCF ID", "USCF Rating", "State", "Section", "Schedule", "Bye(s)"];
      const cells = ['<span id="#bname_101">Synthetic</span>', "Synthetic", "", "", "87654321", "", "NY", "", "", ""];
      return new Response(`<table><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr><tr>${cells.map(c => `<td>${c}</td>`).join("")}</tr></table>`);
    }
    if (url.pathname === "/admin/ajaxRegistrationDataTable.php") {
      const fields = new URLSearchParams(String(init?.body));
      const rows = fields.get("status") === "active" ? [{ eventId: foreignLinks ? "999" : "101",
        tourid: wrongNativeEvent ? "9999" : "4912", order_id: "1", section_menu_name: "",
        createdAt: '<span title="2026-11-01 12:00:00 UTC">2026-11-01 12:00:00<br />(GMT+00:00)</span>' }] : [];
      const count = changedNativeCount && fields.get("length") === "1" ? 2 : rows.length;
      return Response.json({ iTotalRecords: count, iTotalDisplayRecords: count, aaData: rows });
    }
    if (url.pathname === "/admin/invoice.php") return new Response(invoice(family));
    throw new Error("unexpected_source_request");
  }, limit);
  };
  const kv = { get: async (name: string) => store.get(name) ?? null,
    put: async (name: string, value: string) => { store.set(name, value); } } as unknown as KVNamespace;
  const result = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, [card], now, client(limited ? 8 : 42));
  const firstStatus = JSON.parse(store.get(key)!);
  const retry = await collectBatch({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, [card], now + 1000, client());
  const snapshot = JSON.parse(store.get(snapshotKey(family, 2027)) ?? "null");
  return Response.json({ result, retry, firstStatus, sourceCalls,
    missing: (await receiptForecast(card, snapshot, [], now + 1000)).missing,
    status: JSON.parse(store.get(key)!), settingsReads, reportReads,
    snapshot: snapshot ? { family: snapshot.family, year: snapshot.year, registrations: snapshot.registration_count,
      cohort: snapshot.cohort.length, net: snapshot.summary.net_cents } : null,
    sourceRequestsWereReadOnly: requests.every(r => r.method === "GET"
      || ["/admin/set_player_data_for_datatable.php", "/admin/ajaxRegistrationDataTable.php"].includes(r.path)) });
}
