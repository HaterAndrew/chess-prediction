// Only the scheduled collector imports this module; the public Worker has no login secrets.
export type SourceFetch = (url: string, init?: RequestInit) => Promise<Response>;
// @ts-expect-error plain ESM shared with the public proxy and Python parity gate.
import { deriveEntryListCode, entryListUrl } from "../entrylist_codes.mjs";
const ORIGIN = "https://chessaction.com";
const AUTH_PATHS = new Set(["/login.php", "/admin/login.php", "/admin/vsecurelogin.php"]);
const PATHS = new Set([
  "/login.php", "/index.php", "/user_profile.php",
  "/admin/login.php", "/admin/vsecurelogin.php", "/admin/index.php", "/admin/search.php",
  "/admin/set_player_data_for_datatable.php", "/admin/ajaxRegistrationDataTable.php",
  "/admin/ajax_get_txn_total.php", "/admin/invoice.php", "/admin/add_edit_tour.php",
]);
const MAX_BYTES = 8_000_000;

export async function boundedText(response: Response): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) throw new Error("source_too_large");
      chunks.push(value);
    }
  } catch {
    await reader.cancel();
    throw new Error("source_read_failed");
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.length; }
  return new TextDecoder().decode(bytes);
}

export class ChessActionClient {
  private cookies = new Map<string, string>();
  private requests = 0;
  private readonly startedAt = Date.now();

  constructor(private readonly sourceFetch: SourceFetch = (url, init) => fetch(url, init), private readonly requestLimit = 42,
    private readonly maxElapsedMs = 8 * 60_000) {}

  get remainingRequests(): number { return this.remainingMs > 0 ? Math.max(0, this.requestLimit - this.requests) : 0; }
  private get remainingMs(): number { return Math.max(0, this.maxElapsedMs - (Date.now() - this.startedAt)); }

  async publicEntryList(family: string, year: number): Promise<string> {
    const code = deriveEntryListCode(family);
    if (!code || !/^[A-Z]{1,6}$/.test(code) || !Number.isInteger(year) || year < 2020 || year > 2035) throw new Error("public_registration_unavailable");
    const url = new URL(entryListUrl(code, year));
    if (url.origin !== "https://www.chessaction.com" || url.search || url.hash
        || !/^\/tournaments\/advlists\/CCA\/CCA_[A-Z]{1,6}\d{2}\/CCA_[A-Z]{1,6}\d{2}_alp_n\.html$/.test(url.pathname)) throw new Error("source_destination_refused");
    if (!this.remainingMs || ++this.requests > this.requestLimit) throw new Error("source_request_limit");
    let response: Response;
    try {
      // Public list requests never carry the admin cookie, including redirects.
      response = await this.sourceFetch(url.toString(), { headers: { "User-Agent": "Mozilla/5.0 ChessEntries/1.0" }, redirect: "manual", signal: AbortSignal.timeout(Math.min(20_000, this.remainingMs)) });
    } catch { throw new Error(!this.remainingMs ? "source_request_limit" : "public_registration_unavailable"); }
    if (!response.ok) { await response.body?.cancel(); throw new Error("public_registration_unavailable"); }
    return this.readResponse(response);
  }

  async request(path: string, fields?: Record<string, string>, method = "GET"): Promise<string> {
    let url = new URL(path, ORIGIN + "/admin/");
    const authenticationRequest = AUTH_PATHS.has(url.pathname);
    let body = fields && method === "POST" ? new URLSearchParams(fields).toString() : undefined;
    if (fields && method === "GET") url.search = new URLSearchParams(fields).toString();
    for (let redirects = 0; redirects <= 4; redirects++) {
      if (url.origin !== ORIGIN || url.username || url.password || !PATHS.has(url.pathname)) throw new Error("source_destination_refused");
      if (url.pathname === "/admin/add_edit_tour.php" && (method !== "GET"
          || [...url.searchParams.keys()].join() !== "tid" || !/^\d{1,12}$/.test(url.searchParams.get("tid") ?? ""))) throw new Error("source_destination_refused");
      if (!this.remainingMs || ++this.requests > this.requestLimit) throw new Error("source_request_limit");
      const headers = new Headers({ "User-Agent": "Mozilla/5.0 ChessEntries/1.0",
        "Referer": ORIGIN + (["/login.php", "/admin/login.php", "/admin/vsecurelogin.php"].includes(path) ? path : "/admin/search.php") });
      if (url.pathname === "/admin/ajaxRegistrationDataTable.php") {
        headers.set("X-Requested-With", "XMLHttpRequest");
        headers.set("Referer", ORIGIN + "/admin/registrations.php");
      }
      if (this.cookies.size) headers.set("Cookie", [...this.cookies].map(([k, v]) => `${k}=${v}`).join("; "));
      if (body !== undefined) {
        headers.set("Content-Type", "application/x-www-form-urlencoded");
        headers.set("Origin", ORIGIN);
      }
      let response: Response;
      const signal = AbortSignal.timeout(Math.min(60_000, this.remainingMs));
      try {
        response = await this.sourceFetch(url.toString(), {
          method, body, headers, redirect: "manual", signal,
        });
      } catch { throw new Error(!this.remainingMs ? "source_request_limit" : signal.aborted ? "source_timeout" : "source_network_failed"); }
      for (const cookie of response.headers.getSetCookie()) {
        const match = /^([!#$%&'*+.^_`|~\w-]+)=([^;\r\n]*)/.exec(cookie);
        if (match) this.cookies.set(match[1], match[2]);
      }
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        const location = response.headers.get("Location");
        await response.body?.cancel();
        if (!location) throw new Error("source_redirect_failed");
        const target = new URL(location, url);
        if (!authenticationRequest && target.origin === ORIGIN && AUTH_PATHS.has(target.pathname)) {
          throw new Error("source_login_expired");
        }
        url = target;
        if (response.status === 303 || ((response.status === 301 || response.status === 302) && method === "POST")) {
          method = "GET"; body = undefined;
        }
        continue;
      }
      if (!response.ok) { await response.body?.cancel(); throw new Error("source_http_failed"); }
      if (["/admin/login.php", "/admin/vsecurelogin.php", "/login.php"].includes(url.pathname)
          && !["/admin/login.php", "/admin/vsecurelogin.php", "/login.php"].includes(path)) {
        await response.body?.cancel(); throw new Error("source_login_expired");
      }
      return this.readResponse(response);
    }
    throw new Error("source_redirect_failed");
  }

  private async readResponse(response: Response): Promise<string> {
    try { return await boundedText(response); }
    catch (error) {
      if (!this.remainingMs) throw new Error("source_request_limit");
      throw error;
    }
  }

  async login(username: string, password: string): Promise<string> {
    if (!username || !password) throw new Error("source_login_missing");
    const page = await this.request("/admin/login.php");
    let token: string | null = null;
    await new HTMLRewriter().on('input[name="adminlogin"]', {
      element(el) { token = el.getAttribute("value"); },
    }).transform(new Response(page)).text();
    if (token === null) throw new Error("source_login_schema_changed");
    const result = await this.request("/admin/login.php", { username, password, adminlogin: token, submit: "Login" }, "POST");
    if (result.includes("Enter Login Authentication Code")) throw new Error("source_mfa_required");
    return this.ordersPage();
  }

  async resume(cookie: string): Promise<string> {
    if (!cookie || /[\r\n]/.test(cookie) || cookie.length > 16_384) throw new Error("source_session_invalid");
    for (const item of cookie.split(";")) {
      const match = /^\s*([!#$%&'*+.^_`|~\w-]+)=([^;\r\n]*)$/.exec(item);
      if (!match) throw new Error("source_session_invalid");
      this.cookies.set(match[1], match[2]);
    }
    return this.ordersPage();
  }

  private async ordersPage(): Promise<string> {
    const search = await this.request("search.php");
    if (!/id\s*=\s*["']tournments["']/.test(search) || !search.includes("Continental Chess Association")) throw new Error("source_login_failed");
    return search;
  }

  async eventSettings(tournamentId: string): Promise<string> {
    if (!/^\d{1,12}$/.test(tournamentId)) throw new Error("source_destination_refused");
    return this.request("add_edit_tour.php", { tid: tournamentId });
  }

  async invoice(orderId: string): Promise<string> {
    if (!/^\d{1,40}$/.test(orderId)) throw new Error("order_identity_missing");
    return this.request("invoice.php", { oid: orderId });
  }

  filters(tournamentId: string): Record<string, string> {
    if (!/^\d+$/.test(tournamentId)) throw new Error("invalid_tournament");
    return {
      pptxn: "", lname: "", fname: "", ftitles: "all", uscfid: "", ppcon: "0", country: "0",
      state: "All", mem: "0", tname: tournamentId, excludeper: "0", discountClaimed: "0",
      regularDiscountCode: "", additionalFee: "0", sortingOption: "1", sortBy: "paymentDate",
      selectedReportType: "player_tabular_datatable", orderStatus: "Non-Declined",
    };
  }

  async playerRows(tournamentId: string, transaction?: string, orderIds?: string[]): Promise<Record<string, unknown>[]> {
    const rows: Record<string, unknown>[] = [];
    if (orderIds && (tournamentId !== "All" || !transaction || !orderIds.length || orderIds.some(id => !/^\d+$/.test(id)))) throw new Error("source_schema_changed");
    const selectedOrders = orderIds ? new Set(orderIds) : null;
    let received = 0;
    const filters = tournamentId === "All" && transaction && transaction.length <= 200
      ? { ...this.filters("0"), tname: "All", pptxn: transaction }
      : this.filters(tournamentId);
    let total: number | null = null;
    let reportBytes = 0;
    for (let start = 0; start < 10_000; start += 1000) {
      const text = await this.request("set_player_data_for_datatable.php", {
        ...filters, draw: "1", start: String(start), length: "1000",
      }, "POST");
      let page: { recordsFiltered?: number | string; data?: Record<string, unknown>[] };
      try { page = JSON.parse(text); } catch { throw new Error("source_schema_changed"); }
      const filtered = typeof page.recordsFiltered === "string" && /^(0|[1-9]\d*)$/.test(page.recordsFiltered)
        ? Number(page.recordsFiltered) : page.recordsFiltered;
      if (typeof filtered !== "number" || !Number.isSafeInteger(filtered) || filtered < 0 || !Array.isArray(page.data)
          || page.data.length > 1000 || page.data.some(r => !r || typeof r !== "object")) throw new Error("source_schema_changed");
      if (total !== null && total !== filtered) throw new Error("source_changed_during_read");
      total = filtered;
      received += page.data.length;
      // Broad labels such as Cash span years of unrelated orders. Read every
      // source page, retaining every line of only the requested complete orders.
      const selected = selectedOrders ? page.data.filter(row => selectedOrders.has(String(row.order_id ?? ""))) : page.data;
      reportBytes += new TextEncoder().encode(selectedOrders ? JSON.stringify(selected) : text).byteLength;
      if (reportBytes > MAX_BYTES) throw new Error("source_too_many_rows");
      rows.push(...selected);
      if (received === total) return rows;
      if (page.data.length !== 1000 || received > total) throw new Error("source_incomplete");
    }
    throw new Error("source_too_many_rows");
  }
}
