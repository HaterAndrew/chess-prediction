import { describe, expect, it } from "vitest";
import { ChessActionClient } from "./client";
import { isSessionHeartbeat, refreshSession } from "./session";

const now = Date.parse("2026-11-09T03:00:00Z");
const storage = () => {
  const writes = new Map<string, string>();
  const kv = { put: async (key: string, value: string) => { writes.set(key, value); } } as unknown as KVNamespace;
  return { writes, kv };
};

describe("approved-session heartbeat", () => {
  it("recognizes only the configured heartbeat schedules", () => {
    expect(isSessionHeartbeat("*/10 0-1,9-23 * * *")).toBe(true);
    expect(isSessionHeartbeat("0,10,20,40,50 2-8 * * *")).toBe(true);
    expect(isSessionHeartbeat("30 2-8 * * *")).toBe(false);
    expect(isSessionHeartbeat("")).toBe(false);
  });

  it("makes one Orders read and writes only session health", async () => {
    const { kv, writes } = storage();
    const calls: Array<{ path: string; method: string; cookie: string | null }> = [];
    const client = new ChessActionClient(async (url, init) => {
      calls.push({ path: new URL(url).pathname, method: init?.method ?? "GET", cookie: new Headers(init?.headers).get("Cookie") });
      return new Response('<select id="tournments"></select>Continental Chess Association');
    });
    expect(await refreshSession({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, now, client))
      .toEqual({ attempted_at: new Date(now).toISOString(), ok: true, reason: null });
    expect(calls).toEqual([{ path: "/admin/search.php", method: "GET", cookie: "session=synthetic" }]);
    expect([...writes.keys()]).toEqual(["session:status"]);
  });

  it("never requests a login or code when no approved session exists", async () => {
    const { kv } = storage();
    let calls = 0;
    const client = new ChessActionClient(async () => { calls++; throw new Error("unexpected"); });
    expect(await refreshSession({ FINANCE_KV: kv }, now, client))
      .toMatchObject({ ok: false, reason: "source_session_required" });
    expect(calls).toBe(0);
  });

  it("records expiry without submitting any login form", async () => {
    const { kv, writes } = storage();
    const calls: string[] = [];
    const client = new ChessActionClient(async (url, init) => {
      calls.push(`${init?.method ?? "GET"} ${new URL(url).pathname}`);
      return new URL(url).pathname === "/admin/search.php"
        ? new Response(null, { status: 302, headers: { Location: "/admin/login.php" } })
        : new Response("Sign in");
    });
    expect(await refreshSession({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, now, client))
      .toMatchObject({ ok: false, reason: "source_login_expired" });
    expect(calls).toEqual(["GET /admin/search.php"]);
    expect([...writes.keys()]).toEqual(["session:status"]);
  });

  it("propagates a health-storage failure", async () => {
    const kv = { put: async () => { throw new Error("synthetic_storage_failure"); } } as unknown as KVNamespace;
    await expect(refreshSession({ FINANCE_KV: kv }, now)).rejects.toThrow("synthetic_storage_failure");
  });

  it("does not enter a verification page reached from Orders", async () => {
    const { kv } = storage();
    let calls = 0;
    const client = new ChessActionClient(async () => {
      calls++;
      return new Response(null, { status: 302, headers: { Location: "/admin/vsecurelogin.php" } });
    });
    expect(await refreshSession({ FINANCE_KV: kv, CHESS_ACTION_COOKIE: "session=synthetic" }, now, client))
      .toMatchObject({ ok: false, reason: "source_login_expired" });
    expect(calls).toBe(1);
  });
});
