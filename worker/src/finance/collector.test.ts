import { describe, expect, it } from "vitest";
import { collectBatch, safeFailure } from "./collect";
import { ChessActionClient } from "./client";

describe("unattended collector", () => {
  it("does not start a fresh email-code login when no approved session exists", async () => {
    const writes = new Map<string, string>();
    let upstreamCalls = 0;
    const client = new ChessActionClient(async () => { upstreamCalls++; throw new Error("not_expected"); });
    const kv = { put: async (k: string, v: string) => { writes.set(k, v); } } as unknown as KVNamespace;
    expect(await collectBatch({ FINANCE_KV: kv }, [], Date.now(), client)).toEqual({ collected: 0, failed: 1 });
    expect(upstreamCalls).toBe(0);
    expect(JSON.parse(writes.get("collector:status")!)).toMatchObject({ ok: false, reason: "source_session_required" });
  });
  it("never logs arbitrary source exceptions that could contain private data", () => {
    expect(safeFailure(new Error("synthetic-password-or-response"))).toBe("collection_failed");
    expect(safeFailure(new Error("source_login_expired"))).toBe("source_login_expired");
  });
});
