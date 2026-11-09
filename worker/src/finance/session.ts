import { ChessActionClient } from "./client";
import { safeFailure } from "./collect";
import type { FinanceEnv } from "./collect";
import type { CollectorStatus } from "./store";

// Retain the former expressions while already queued events finish rolling out.
const HEARTBEATS = ["10,30,50 * * * *", "*/10 0-1,9-23 * * *", "0,10,20,40,50 2-8 * * *"];

export const isSessionHeartbeat = (cron: string | undefined): boolean =>
  typeof cron === "string" && HEARTBEATS.includes(cron);

// Reuse the approved session without collecting payments or submitting login
// forms. This can prevent an idle timeout; it cannot renew absolute expiry.
export async function refreshSession(env: FinanceEnv, now = Date.now(),
  client = new ChessActionClient(undefined, 4, 20_000)): Promise<CollectorStatus> {
  if (!env.FINANCE_KV) throw new Error("finance_storage_missing");
  let status: CollectorStatus = { attempted_at: new Date(now).toISOString(), ok: false, reason: "source_session_required" };
  if (env.CHESS_ACTION_COOKIE) {
    try {
      await client.resume(env.CHESS_ACTION_COOKIE);
      status = { ...status, ok: true, reason: null };
    } catch (error) { status = { ...status, reason: safeFailure(error) }; }
  }
  await env.FINANCE_KV.put("session:status", JSON.stringify(status));
  return status;
}
