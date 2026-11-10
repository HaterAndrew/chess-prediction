import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Miniflare, Log, LogLevel, convertV4MiniflareOptions } from "miniflare";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { isSessionHeartbeat } from "./session";

let runtime;
let rpcRuntime;
function bundle(config, main) {
  const output = mkdtempSync(join(tmpdir(), "chess-finance-rpc-"));
  const command = spawnSync(process.execPath, [
    fileURLToPath(new URL("../../node_modules/wrangler/bin/wrangler.js", import.meta.url)),
    "deploy", ...(main ? [main] : []), "--dry-run", "--config", config, "--outdir", output,
  ], { encoding: "utf8" });
  if (command.status !== 0) throw new Error(command.stderr + command.stdout);
  const script = readdirSync(output).find(p => p.endsWith(".js"));
  if (!script) throw new Error("No compiled RPC harness");
  return { modules: true, modulesRoot: output, scriptPath: join(output, script), compatibilityDate: "2026-10-30" };
}
beforeAll(async () => {
  const output = mkdtempSync(join(tmpdir(), "chess-finance-runtime-"));
  const command = spawnSync(process.execPath, [
    fileURLToPath(new URL("../../node_modules/wrangler/bin/wrangler.js", import.meta.url)),
    "deploy", "--dry-run", "--config", fileURLToPath(new URL("../../runtime-tests/wrangler.toml", import.meta.url)),
    "--outdir", output,
  ], { encoding: "utf8" });
  if (command.status !== 0) throw new Error(command.stderr + command.stdout);
  const script = readdirSync(output).find(p => p.endsWith(".js"));
  if (!script) throw new Error("No compiled runtime harness");
  runtime = new Miniflare(convertV4MiniflareOptions({ modules: true, modulesRoot: output, scriptPath: join(output, script), compatibilityDate: "2026-10-30", log: new Log(LogLevel.ERROR),
    outboundService: async request => new URL(request.url).hostname === "chessentries.com" ? Response.json({ tournaments: [] })
      : new Response("<h1>Continental Chess Association</h1><select id='tournments'></select>") }));
  await runtime.ready;
}, 30_000);
afterAll(async () => { await Promise.all([runtime?.dispose(), rpcRuntime?.dispose()]); });

async function invoke(path, body) {
  const response = await runtime.dispatchFetch("https://local.test" + path, { method: "POST", body: JSON.stringify(body) });
  return { status: response.status, body: await response.json() };
}

const summaryHtml = `<table><thead><tr>
<th>Tournament fees ($) <br>[Cart Discounts deducted]</th><th>Primary membership fees ($)</th>
<th>PayPal/Credit Card Fee Contributions ($)</th><th>Other fees ($)</th><th>Refunded ($)</th><th>Gross Revenue ($)</th>
</tr></thead><tbody><tr><td>100.00</td><td>10.00</td><td>3.00</td><td>2.00</td><td>15.00</td><td>100.00</td></tr></tbody></table>`;

describe("native Worker source boundaries", () => {
  it("bounds attempted writes and preserves publication ordering at every storage failure", async () => {
    const results = (await invoke("/quota-faults", {})).body;
    expect(results).toHaveLength(results[0].writes + 2);
    for (const result of results) {
      expect(result.failureReached).toBe(result.failAt !== 0);
      expect(result.writes).toBeLessThanOrEqual(12);
      expect(result.unpersistedResume).toBe(false);
      expect(result.publicationWithoutFence).toBe(false);
    }
    expect(results.some(result => result.trace.filter(key => key === "collector").length === 2)).toBe(true);
  });
  it("defers ordinary shared carts exhausted by leftover invocation requests", async () => {
    expect((await invoke("/leftover-budget", {})).body).toEqual({ first: { collected: 1, failed: 1 }, resume: true,
      second: { collected: 1, failed: 0 }, net: 1000 });
  });
  it("requires newly staged proofs to persist before claiming resumable progress", async () => {
    expect((await invoke("/resume-persistence", {})).body).toEqual([
      { failCheckpoint: false, rejected: false, attempts: 2, beforeProofs: 1, afterProofs: 2, resume: true },
      { failCheckpoint: true, rejected: true, attempts: 2, beforeProofs: 1, afterProofs: 1, resume: null },
    ]);
  });
  it("does not retry indefinitely when only an unchanged prefix can be reused", async () => {
    expect((await invoke("/zero-progress", {})).body).toEqual([
      { result: { collected: 0, failed: 1 }, resume: true },
      { result: { collected: 0, failed: 1 }, resume: false },
      { result: { collected: 0, failed: 0 }, resume: false },
    ]);
  });
  it("stays within the free daily write allowance during bootstrap and next-day collection", async () => {
    const config = readFileSync(new URL("../../wrangler.finance.toml", import.meta.url), "utf8");
    const schedules = JSON.parse(/^crons\s*=\s*(\[[^\n]+\])/m.exec(config)[1]);
    const slots = [];
    for (const cron of schedules) {
      const [minutes, hours, ...calendar] = cron.split(" ");
      expect(hours).toBe("*"); expect(calendar).toEqual(["*", "*", "*"]);
      for (let hour = 0; hour < 24; hour++) for (const minute of minutes.split(",").map(Number)) {
        slots.push({ minute: hour * 60 + minute, heartbeat: isSessionHeartbeat(cron) });
      }
    }
    slots.sort((a, b) => a.minute - b.minute);
    expect(slots.filter(slot => !slot.heartbeat)).toHaveLength(72);
    expect(slots.filter(slot => slot.heartbeat)).toHaveLength(72);
    const result = (await invoke("/quota-days", slots)).body;
    console.info("quota_rehearsal", JSON.stringify(result));
    for (const day of result.days) {
      expect(day.writes).toBeLessThanOrEqual(936);
      expect(day.maximumBatch).toBeLessThanOrEqual(12);
      expect(day.maximumHeartbeat).toBe(1);
      expect(day.completed).toBe(36); expect(day.snapshots).toBe(36);
      expect(day.conserved).toBe(true); expect(day.checkpointWritesArePerEvent).toBe(true);
    }
  }, 30_000);
  it("routes the heartbeat to session health without starting a financial batch", async () => {
    expect((await invoke("/session-missing", {})).body).toMatchObject({
      rejected: true, session: { ok: false, reason: "source_session_required" }, financial_status_written: false,
    });
  });
  it("proves invoice cart membership and rejects hidden or additional players", async () => {
    const player = (event, section, subtotal) => `<div class="invoicetname">Tournamen Name: ${event}</div><div class="invoicekey">Player's Name: Synthetic Person</div><div class="invoicekey">Section: ${section}</div><div class="invoicevaluesub">Sub Total</div><div class="invoicevalueextend">US $ ${subtotal}</div>`;
    const document = lines => `<html><head><script>/* Never executed */</script></head><body><div id="invoicecontents">${lines}<div class="invoicevaluesub">PayPal Contribution</div><div class="invoicevalueextend">US $0.00</div><div class="invoicevaluesub">Grand Total</div><div class="invoicevalueextend">US $10.00</div><div class="invoicefotter">Footer</div></div></body></html>`;
    const expected = [{ tournament: "2026 Example Open", section: "Open", order_value: "10.00", paypal_credit_card_fee_contribution: "" }];
    const one = player("2026 Example Open", "Open", "10.00");
    expect((await invoke("/invoice-proof", { html: document(one), expected })).body).toEqual({ whole: true });
    const extra = player("2026 Another Open", "Open", "0.00");
    expect((await invoke("/invoice-proof", { html: document(one + extra), expected })).body).toEqual({ whole: false });
    const extraClasses = extra.replaceAll('class="', 'class="extra ');
    expect((await invoke("/invoice-proof", { html: document(one + extraClasses), expected })).body.error).toBe("invoice_schema_changed");
    expect((await invoke("/invoice-proof", { html: document(one + extra), expected: [{ ...expected[0], order_value: "11.00" }] })).body.error).toBe("order_reconciliation_failed");
    for (const hidden of [`<textarea>${extra}</textarea>`, `<!--${extra}-->`, `<!cart-note>`, `<br class="invoicekey">`, `<?cart-note>`, `<script>${extra}</script>`, `<template>${extra}</template>`, `<svg>${extra}</svg>`]) {
      expect((await invoke("/invoice-proof", { html: document(one + hidden), expected })).body.error).toBe("invoice_schema_changed");
    }
    expect((await invoke("/invoice-proof", { html: document(one).replace('class="invoicefotter"', 'class="unknown"'), expected })).body.error).toBe("invoice_schema_changed");
    expect((await invoke("/invoice-proof", { html: document(one), expected: [{ ...expected[0], order_value: "11.00" }] })).body.error).toBe("order_reconciliation_failed");
  });
  it("reads public registration IDs without retaining names", async () => {
    const headers = ["Player's Name", "Player's Name", "FIDE ID", "FIDE Rating", "USCF ID", "USCF Rating", "State", "Section", "Schedule", "Bye(s)"];
    const html = `<table><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr><tr><td><span id="#bname_101">Synthetic, Player</span></td><td><span id="#bname_101">Player Synthetic</span></td><td>1234567 [USA]</td><td>1000</td><td>12345678</td><td>1000</td><td>CA</td><td>Open</td><td>3 Day</td><td></td></tr></table>`;
    expect((await invoke("/public-cohort", { html })).body).toEqual([{ id: "101", uscf: "12345678", fide: "1234567" }]);
    expect((await invoke("/public-cohort", { html: html.replace("USCF ID", "Unknown") })).body.error).toBe("public_registration_schema_changed");
  });
  it("keeps the admin cookie out of public-list requests", async () => {
    const result = await invoke("/public-fetch", { replies: [
      { text: `<h1>Continental Chess Association</h1><select id='tournments'></select>` }, { text: "Public list" },
    ] });
    expect(result.body.calls[0].cookie).toBe(true);
    expect(result.body.calls[1].cookie).toBe(false);
    expect(result.body.calls[1].path).toBe("/tournaments/advlists/CCA/CCA_LAO26/CCA_LAO26_alp_n.html");
  });
  it("uses the native global fetch through the default client transport", async () => {
    expect((await invoke("/default-fetch", {})).body).toEqual({ ok: true });
  });
  it("uses the default native transport for anonymous public lists", async () => {
    expect((await invoke("/default-public-fetch", {})).body).toEqual({ ok: true });
  });
  it("runs the real scheduled handler without unsupported fetch redirect modes", async () => {
    expect((await invoke("/scheduled", {})).body).toMatchObject({ ok: false, reason: "source_session_required" });
  });
  it("gives live work first access after a costly successful calibration batch", async () => {
    const result = (await invoke("/costly-calibration", {})).body;
    expect(result.attempted).toHaveLength(2);
    expect(["2", "3"]).toContain(result.attempted[0]);
    expect(result.attempted[1]).toBe("1");
    expect(result.batches).toEqual([{ collected: 1, failed: 0 }, { collected: 1, failed: 0 }]);
  });
  it("attempts reserved calibration before live work can exhaust the request budget", async () => {
    expect((await invoke("/budget-priority", {})).body).toEqual({ attempted: ["2"] });
  });
  it("rebuilds damaged pooled history from a reconciled source snapshot", async () => {
    expect((await invoke("/repair?corrupt=1", {})).body).toEqual({ first: { collected: 1, failed: 0 },
      freshAfterFailure: true, second: { collected: 1, failed: 0 }, historyPresent: true, snapshotPresent: true });
  });
  it("repairs an interrupted calibration write before publishing a fresh snapshot", async () => {
    expect((await invoke("/repair", {})).body).toEqual({ first: { collected: 0, failed: 1 },
      freshAfterFailure: false, second: { collected: 1, failed: 0 }, historyPresent: true, snapshotPresent: true });
  });
  it("routes authorized requests through the named private RPC and isolates previews", async () => {
    const hash = value => createHash("sha256").update(value).digest("hex");
    const now = Date.now();
    const asOf = new Date(now - 60_000).toISOString();
    const observed = new Date(now - 120_000).toISOString();
    const paid = new Date(now - 86_400_000).toISOString();
    const start = new Date(now + 10 * 86_400_000).toISOString().slice(0, 10);
    const id = hash("1");
    const card = { family: "Example Open", year: 2026, status: "live", current_count: 1,
      point_estimate: 2, regular_fee: 10, event_start: start, count_observed_at: observed, count_cohort_hash: hash(id) };
    const snapshot = { schema: 1, family: card.family, year: 2026, tournament_id: "123", source_as_of: asOf,
      event_start: start, registration_close: start, regular_fee_cents: 1000, registration_count: 1,
      cohort: [{ id, paid_at: paid }], summary: { entry_cents: 1000, membership_cents: 0,
        contribution_cents: 0, other_cents: 0, refunded_cents: 0, net_cents: 1000 },
      buckets: [{ days_before: 2, registrations: 1, entry_cents: 1000, membership_cents: 0, contribution_cents: 0, other_cents: 0 }],
      previous_net_cents: null, previous_as_of: null };
    const publicScript = bundle(fileURLToPath(new URL("../../runtime-tests/wrangler.toml", import.meta.url)),
      fileURLToPath(new URL("../../runtime-tests/rpc.ts", import.meta.url)));
    const financeScript = bundle(fileURLToPath(new URL("../../wrangler.finance.toml", import.meta.url)));
    const bindings = { ALLOWED_ORIGIN: "https://local.test", ENTRY_VALUE_MODE: "receipts",
      TEST_DATA: { generated: asOf, tournaments: [card] } };
    rpcRuntime = new Miniflare(convertV4MiniflareOptions({ log: new Log(LogLevel.ERROR), workers: [
      { ...publicScript, name: "public", bindings: { ...bindings, ENTRY_VALUE_KEY: "synthetic", ENTRY_VALUE_KEY_SECONDARY: "synthetic-secondary" }, kvNamespaces: { KV: "limiter" },
        serviceBindings: { FINANCE: { name: "finance", entrypoint: "ReceiptService" } } },
      { ...financeScript, name: "finance", kvNamespaces: { FINANCE_KV: "receipts" } },
      { ...publicScript, name: "preview", bindings, kvNamespaces: { KV: "preview-limiter" } },
    ] }));
    await rpcRuntime.ready;
    const kv = await rpcRuntime.getKVNamespace("FINANCE_KV", "finance");
    await kv.put("receipts:Example%20Open:2026", JSON.stringify(snapshot));
    await kv.put("history:Example%20Open", JSON.stringify([{ ...snapshot, year: 2025, registration_close: "2025-11-15" }]));
    const request = key => ({ headers: { "X-Value-Key": key } });
    const allowed = await rpcRuntime.dispatchFetch("https://local.test/entry-value", request("synthetic"));
    expect(allowed.status).toBe(200);
    expect(allowed.headers.get("Cache-Control")).toBe("no-store");
    expect((await allowed.json()).events[0]).toMatchObject({ value: 20, basis: "chess_action_receipts" });
    const additional = await rpcRuntime.dispatchFetch("https://local.test/entry-value", request("synthetic-secondary"));
    expect(additional.status).toBe(200);
    expect(additional.headers.get("Cache-Control")).toBe("no-store");
    expect((await additional.json()).events[0]).toMatchObject({ value: 20, basis: "chess_action_receipts" });
    await kv.put("receipts:Example%20Open:2026", JSON.stringify({ ...snapshot, registration_close: null }));
    const unknownClose = await rpcRuntime.dispatchFetch("https://local.test/entry-value", request("synthetic"));
    expect(unknownClose.status).toBe(200);
    expect((await unknownClose.json()).events[0]).toMatchObject({ value: 20, missing: null });
    expect((await rpcRuntime.dispatchFetch("https://local.test/entry-value", request("wrong"))).status).toBe(401);
    expect((await rpcRuntime.dispatchFetch("https://local.test/entry-value", { headers: {
      "X-Value-Key": "synthetic", Origin: "https://attacker.invalid",
    } })).status).toBe(403);
    const finance = await rpcRuntime.getWorker("finance");
    expect((await finance.fetch("https://local.test/entry-value")).status).toBe(404);
    const preview = await rpcRuntime.getWorker("preview");
    expect((await preview.fetch("https://local.test/entry-value", request("synthetic"))).status).toBe(403);
    expect((await preview.fetch("https://local.test/entry-value", request("synthetic-secondary"))).status).toBe(403);
    await kv.put("session:status", JSON.stringify({ ok: "false", attempted_at: "invalid", reason: null }));
    const malformed = await rpcRuntime.dispatchFetch("https://local.test/entry-value", request("synthetic"));
    expect(malformed.status).toBe(502);
    expect(await malformed.json()).toEqual({ error: "data_unavailable" });
  }, 30_000);
  it("advances beyond failed early events and refreshes completed-only families", async () => {
    expect((await invoke("/scheduler", {})).body).toEqual({ attempted: 13, finished_attempted: true });
  });
  it("retries repaired calendar failures without removing unrelated backoff", async () => {
    expect((await invoke("/calendar-retry", {})).body).toEqual({ attempted: ["1"], unrelatedUnchanged: true, missingUnchanged: true });
  });
  it("exposes no financial HTTP endpoint, even if a route is accidentally added", async () => {
    expect((await invoke("/http-is-private", {})).body).toEqual({ status: 404 });
  });
  it("reports an expired approved session without starting a new password login", async () => {
    const result = await invoke("/resume", { replies: [{ text: "", status: 302, location: "/admin/login.php" }, { text: "Sign in" }] });
    expect(result.body.error).toBe("source_login_expired");
  });
  it("reports a redirect to the admin MFA page as session expiry", async () => {
    const result = await invoke("/resume", { replies: [{ text: "", status: 302, location: "/admin/vsecurelogin.php" }, { text: "Enter Login Authentication Code" }] });
    expect(result.body.error).toBe("source_login_expired");
  });
  it("recognizes an email-code challenge and stops before loading reports", async () => {
    const result = await invoke("/login", { replies: [
      { text: `<input name='adminlogin' value='1'>` }, { text: "Enter Login Authentication Code" },
    ] });
    expect(result.body.error).toBe("source_mfa_required");
  });
  it("refuses a public account form before submitting admin credentials", async () => {
    expect((await invoke("/login", { replies: [{ text: `<input name='regforpay' value='1'>` }] })).body.error)
      .toBe("source_login_schema_changed");
  });
  it("parses summary components with the native streaming HTML parser", async () => {
    expect(await invoke("/summary", { html: summaryHtml })).toEqual({ status: 200, body: {
      entry_cents: 10000, membership_cents: 1000, contribution_cents: 300, other_cents: 200,
      refunded_cents: 1500, net_cents: 10000,
    } });
  });
  it("rejects missing columns and inconsistent summaries", async () => {
    expect((await invoke("/summary", { html: summaryHtml.replace("Gross Revenue ($)", "Total") })).status).toBe(422);
    expect((await invoke("/summary", { html: summaryHtml.replace("15.00", "16.00") })).body.error).toBe("summary_mismatch");
  });
  it("ignores non-event tournament options", async () => {
    expect((await invoke("/options", { html: `<select id='tournments'><option value='-1'>Last year</option><option value='123'>2026 Example Open</option></select>` })).body)
      .toEqual([{ id: "123", title: "2026 Example Open" }]);
  });
  it("signs in, retains same-site cookies and checks Orders access", async () => {
    const result = await invoke("/login", { replies: [
      { text: `<input name='adminlogin' value='1'>`, cookie: "session=synthetic; Secure; HttpOnly" },
      { text: "", status: 302, location: "/admin/index.php" }, { text: "Dashboard" },
      { text: `<h2>Continental Chess Association</h2><select id='tournments'></select>` },
    ] });
    expect(result.body.ok).toBe(true);
    expect(result.body.calls).toEqual([
      { path: "/admin/login.php", method: "GET", cookie: false },
      { path: "/admin/login.php", method: "POST", cookie: true },
      { path: "/admin/index.php", method: "GET", cookie: true },
      { path: "/admin/search.php", method: "GET", cookie: true },
    ]);
  });
  it("never forwards login secrets or cookies through foreign redirects", async () => {
    const result = await invoke("/login", { replies: [
      { text: `<input name='adminlogin' value='1'>` },
      { text: "", status: 307, location: "https://attacker.invalid/collect" },
    ] });
    expect(result.body.error).toBe("source_destination_refused");
  });
  it("refuses incomplete source pagination", async () => {
    const result = await invoke("/pages", { replies: [{ text: JSON.stringify({ recordsFiltered: 2, data: [{}] }) }] });
    expect(result.body.error).toBe("source_incomplete");
  });
  it("accepts the source's digit-string record count and still enforces completeness", async () => {
    expect((await invoke("/pages", { replies: [{ text: JSON.stringify({ recordsFiltered: "1", data: [{}] }) }] })).body.count).toBe(1);
    expect((await invoke("/pages", { replies: [{ text: JSON.stringify({ recordsFiltered: "2", data: [{}] }) }] })).body.error).toBe("source_incomplete");
  });
  it("does not coerce malformed string record counts", async () => {
    for (const count of ["", "1.0", "1bad", "-1", "1e3"]) {
      expect((await invoke("/pages", { replies: [{ text: JSON.stringify({ recordsFiltered: count, data: [] }) }] })).body.error).toBe("source_schema_changed");
    }
  });
});
