// Native local harness only; neither production entrypoint imports it.
import { ChessActionClient } from "../src/finance/client";
import { collectRegistrations } from "../src/finance/registration-collect";
import { registrationKey, registrationRecords } from "../src/finance/registration-store";

export async function mappingRecovery(request: Request): Promise<Response> {
  const { mode = "repair" } = await request.json() as { mode?: string };
  const now = Date.parse("2026-11-12T02:40:00Z");
  const legacy = { family: "New York State Senior Championship With Young Adult Mi", year: 2026,
    status: "complete", event_start: "2026-03-01" };
  const ordinary = { family: "Earlier Historical Open", year: 2026, status: "complete", event_start: "2026-10-01" };
  const store = new Map<string, string>();
  store.set(registrationKey(legacy), JSON.stringify({ attempted_at: new Date(now - 3_600_000).toISOString(),
    ok: false, reason: "unmapped_tournament", data: null, retry: false,
    ...(mode === "current" ? { source_policy_version: 1 } : mode === "future" ? { source_policy_version: 2 } : {}) }));
  let puts = 0;
  const kv = { get: async (key: string | string[]) => Array.isArray(key)
    ? new Map(key.map(k => [k, store.get(k) ?? null])) : store.get(key) ?? null,
    put: async (key: string, value: string) => { puts++; store.set(key, value); } } as unknown as KVNamespace;
  const attempts: Array<{ calls: number; ids: string[] }> = [];
  const client = (limit: number) => {
    const attempt = { calls: 0, ids: [] as string[] }; attempts.push(attempt);
    return new ChessActionClient(async (raw, init) => {
      attempt.calls++;
      const path = new URL(raw).pathname;
      if (path === "/admin/search.php") {
        const title = "2026 New York State Senior Championship (With Young Adult/Middle Age Section)";
        return new Response(`<h1>Continental Chess Association</h1><select id="tournments"><option value="2">2026 Earlier Historical Open</option>${mode === "absent" ? "" : `<option value="4182">${title}</option>`}${mode === "ambiguous" ? `<option value="9999">${title}</option>` : ""}</select>`);
      }
      if (path !== "/admin/ajaxRegistrationDataTable.php" || init?.method !== "POST") throw new Error("unexpected_source_request");
      const fields = new URLSearchParams(String(init.body));
      const id = fields.get("tournment")!; attempt.ids.push(id);
      const rows = fields.get("status") === "active" ? [{ eventId: "1",
        tourid: mode === "identity" && id === "4182" ? "999" : id,
        createdAt: '<span title="2026-01-01 12:00:00 UTC">2026-01-01 12:00:00<br />(GMT+00:00)</span>' }] : [];
      return Response.json({ aaData: rows, iTotalRecords: rows.length, iTotalDisplayRecords: rows.length });
    }, limit);
  };
  const firstLimit = mode === "limited" ? 5 : 6;
  const first = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" },
    [ordinary, legacy], now, client(firstLimit));
  const firstRecord = JSON.parse(store.get(registrationKey(legacy))!);
  const firstPuts = puts;
  const second = await collectRegistrations({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" },
    [ordinary, legacy], now + 1000, client(6));
  return Response.json({ first, second, firstRecord, finalRecord: JSON.parse(store.get(registrationKey(legacy))!),
    records: await registrationRecords(kv, [ordinary, legacy], now + 1000), attempts, firstLimit, firstPuts, secondPuts: puts - firstPuts });
}
