import { WorkerEntrypoint } from "cloudflare:workers";
import { boundedText } from "./client";
import { collectBatch } from "./collect";
import type { FinanceEnv } from "./collect";
import { receiptValues } from "./store";
import type { ReceiptCard } from "./types";
import { isSessionHeartbeat, refreshSession } from "./session";
import { ChessActionClient } from "./client";
import { collectRegistrations, isRegistrationTick } from "./registration-collect";
import type { RegistrationCard } from "./registrations";
import { registrationFeedRecords } from "./registration-store";
import { FinanceWriteBudget } from "./write-budget";

export interface FinanceRequest {
  generated: string;
  is_stale?: boolean;
  tournaments: ReceiptCard[];
}

// RPC is available to configured service bindings, never HTTP callers.
export class ReceiptService extends WorkerEntrypoint<FinanceEnv> {
  async fetch(): Promise<Response> { return new Response(null, { status: 404 }); }

  async registrations(cards: RegistrationCard[]) {
    if (!Array.isArray(cards) || cards.length > 2000 || JSON.stringify(cards).length > 1_000_000) throw new Error("invalid_request");
    return { version: 1 as const, generated: new Date().toISOString(), records: (await registrationFeedRecords(this.env.FINANCE_KV, cards)).map(r => ({
      family: r.family, year: r.year, attempted_at: r.attempted_at, ok: r.ok, reason: r.reason, data: r.data,
    })) };
  }

  async receipts(body: FinanceRequest) {
    if (!body || !Array.isArray(body.tournaments) || body.tournaments.length > 2000
        || typeof body.generated !== "string" || JSON.stringify(body).length > 1_000_000) throw new Error("invalid_request");
    let events = await receiptValues(this.env.FINANCE_KV, body.tournaments);
    if (body.is_stale) events = events.map(ev => ({ ...ev, stale: true, missing: "stale_model" }));
    return { generated: body.generated, mode: "receipts" as const, events };
  }
}

export default {
  // Even an accidental HTTP route cannot expose the RPC method or financial data.
  async fetch(): Promise<Response> { return new Response(null, { status: 404 }); },
  async scheduled(_controller: ScheduledController, env: FinanceEnv): Promise<void> {
    if (isSessionHeartbeat(_controller.cron)) {
      const status = await refreshSession(env);
      console.log(JSON.stringify({ event: "finance_session_refresh", ok: status.ok, reason: status.reason }));
      if (!status.ok) throw new Error("finance_session_refresh_failed");
      return;
    }
    const training = isRegistrationTick(_controller.scheduledTime);
    const writes = new FinanceWriteBudget(env.FINANCE_KV);
    try {
      const response = await fetch("https://chessentries.com/data/website_data.json", {
        redirect: "manual", signal: AbortSignal.timeout(20_000),
      });
      if (!response.ok) throw new Error("forecast_source_unavailable");
      const data = JSON.parse(await boundedText(response)) as FinanceRequest;
      if (data.is_stale || !Array.isArray(data.tournaments) || data.tournaments.length > 2000) throw new Error("forecast_source_unavailable");
      const result = training
        ? await collectRegistrations(env, data.tournaments, Date.now(), new ChessActionClient(), writes)
        : await collectBatch(env, data.tournaments, Date.now(), new ChessActionClient(), writes);
      console.log(JSON.stringify({ event: training ? "registration_collection" : "finance_collection", ...result }));
    } catch {
      await writes.kv.put(training ? "registration_collector:status" : "collector:status", JSON.stringify({ attempted_at: new Date().toISOString(), ok: false, reason: "collection_failed" }));
      console.error(JSON.stringify({ event: training ? "registration_collection_failed" : "finance_collection_failed" }));
      throw new Error(training ? "registration_collection_failed" : "finance_collection_failed");
    }
  },
};
