// Routing only (W1): the implementation lives in env / http / limits /
// agent / cca-proxy. entrylist_codes.mjs deliberately stays where the
// Python parity test pins it.
import Anthropic from "@anthropic-ai/sdk";

import { cachedFileId, loadData, runAgentLoop, type CachedData } from "./agent";
import type { AskRequest, Env } from "./env";
import { corsPreflight, jsonResponse } from "./http";
import { checkDailyBudget, checkRateLimit, recordCost } from "./limits";
import { proxyCcaEntryList, proxyCcaTourList } from "./cca-proxy";

export type { Env };

export default {
  // `ctx` is intentionally unused: cost is now recorded inline per turn (v3 S4)
  // rather than deferred through ctx.waitUntil after the loop finished.
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") return corsPreflight(env, request);

    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return jsonResponse({ ok: true, model: env.MODEL, file_id: cachedFileId() }, { status: 200 }, env, request);
    }
    if (url.pathname === "/cca-tourlist") {
      return proxyCcaTourList(env, request);
    }
    if (url.pathname === "/cca-entrylist" && request.method === "GET") {
      return proxyCcaEntryList(env, request);
    }
    if (url.pathname !== "/ask" || request.method !== "POST") {
      return jsonResponse({ error: "Not found" }, { status: 404 }, env, request);
    }

    const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
    const rl = await checkRateLimit(env, ip);
    if (!rl.ok) {
      return jsonResponse(
        { error: "rate_limited", message: "Too many questions in a short time — wait a minute." },
        { status: 429, headers: { "Retry-After": String(rl.retryAfter ?? 60) } },
        env,
        request
      );
    }

    const budget = await checkDailyBudget(env);
    if (!budget.ok) {
      return jsonResponse(
        {
          error: "daily_budget_exhausted",
          message: "Reached today's question limit — try again tomorrow.",
        },
        { status: 503 },
        env,
        request
      );
    }

    let body: AskRequest;
    try {
      body = (await request.json()) as AskRequest;
    } catch {
      return jsonResponse({ error: "bad_request", message: "Invalid JSON body." }, { status: 400 }, env, request);
    }
    if (!body.question || typeof body.question !== "string" || body.question.length > 2000) {
      return jsonResponse(
        { error: "bad_request", message: "Provide a 'question' string under 2000 chars." },
        { status: 400 },
        env,
        request
      );
    }

    if (!env.ANTHROPIC_API_KEY) {
      return jsonResponse(
        {
          error: "no_api_key",
          message:
            "Worker has no ANTHROPIC_API_KEY configured. Set it via `wrangler secret put ANTHROPIC_API_KEY` (prod) or in `.dev.vars` (local).",
          fallback_search: body.question,
        },
        { status: 503 },
        env,
        request
      );
    }

    const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });

    let cd: CachedData;
    try {
      cd = await loadData(env, client);
    } catch (e) {
      return jsonResponse(
        {
          error: "data_unavailable",
          message: `Could not load tournament data: ${(e as Error).message}`,
        },
        { status: 502 },
        env,
        request
      );
    }

    try {
      // v3 S4: bill each turn as it completes and stop as soon as the cap is
      // hit, rather than recording the whole request's cost afterwards via
      // waitUntil (which let a request run its full eight turns unbilled, and
      // left concurrent requests reading a counter nobody had updated yet).
      const result = await runAgentLoop(client, env.MODEL, body, cd, async (delta) => {
        await recordCost(env, delta);
        const b = await checkDailyBudget(env);
        return b.ok;
      });
      return jsonResponse(
        {
          ...result,
          model: env.MODEL,
          data_generated: cd.data.generated,
          file_mounted: !!cd.fileId,
        },
        { status: 200 },
        env,
        request
      );
    } catch (e) {
      const msg = (e as Error).message ?? "unknown";
      return jsonResponse(
        {
          error: "model_error",
          message: `Model call failed: ${msg}`,
          fallback_search: body.question,
        },
        { status: 502 },
        env,
        request
      );
    }
  },
};
