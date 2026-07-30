import Anthropic from "@anthropic-ai/sdk";
import { TOOLS, CODE_EXECUTION_TOOL, buildIndex, runTool, type WebsiteData } from "./tools";
import { systemPrompt } from "./prompts";
// @ts-expect-error plain ESM shared with node (pytest parity gate); no types.
import { deriveEntryListCode, entryListUrl } from "./entrylist_codes.mjs";

export interface Env {
  ANTHROPIC_API_KEY: string;
  ALLOWED_ORIGIN: string;
  DATA_URL: string;
  MODEL: string;
  DAILY_BUDGET_USD: string;
  RATE_LIMIT_PER_MIN: string;
  KV?: KVNamespace;
  // Shared secret gating the /cca-tourlist scrape proxy (see proxyCcaTourList).
  CCA_PROXY_KEY?: string;
}

interface AskRequest {
  question: string;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
}

interface CachedData {
  data: WebsiteData;
  index: string;
  fetchedAt: number;
  fileId: string | null;
  fileUploadedAt: number;
}

const DATA_TTL_MS = 10 * 60 * 1000;
const FILE_TTL_MS = 12 * 60 * 60 * 1000; // re-upload daily-ish
const DATA_MOUNT_PATH = "/mnt/user-upload/website_data.json";

let cached: CachedData | null = null;

async function loadData(env: Env, client: Anthropic): Promise<CachedData> {
  const now = Date.now();
  const dataStale = !cached || now - cached.fetchedAt >= DATA_TTL_MS;
  const fileStale = !cached || !cached.fileId || now - cached.fileUploadedAt >= FILE_TTL_MS;

  if (!dataStale && !fileStale) return cached!;

  if (dataStale) {
    const resp = await fetch(env.DATA_URL, { cf: { cacheTtl: 300 } as RequestInitCfProperties });
    if (!resp.ok) throw new Error(`Data fetch failed: ${resp.status}`);
    const data = (await resp.json()) as WebsiteData;
    cached = {
      data,
      index: buildIndex(data),
      fetchedAt: now,
      fileId: cached?.fileId ?? null,
      fileUploadedAt: cached?.fileUploadedAt ?? 0,
    };
  }

  if (fileStale && cached) {
    try {
      const body = JSON.stringify(cached.data);
      const file = new File([body], "website_data.json", { type: "application/json" });
      const uploaded = await client.beta.files.upload(
        { file },
        { headers: { "anthropic-beta": "files-api-2025-04-14" } }
      );
      cached.fileId = uploaded.id;
      cached.fileUploadedAt = now;
    } catch (e) {
      // Soft-fail file upload: requests proceed with the existing fileId (if any)
      // or without code execution access (the model can still answer from tools).
      console.warn("Files API upload failed:", (e as Error).message);
    }
  }

  return cached!;
}

export function pickAllowedOrigin(env: Env, request: Request): string {
  const allow = env.ALLOWED_ORIGIN.split(",").map((s) => s.trim()).filter(Boolean);
  const origin = request.headers.get("Origin");
  if (!origin) return allow[0] ?? "https://haterandrew.github.io";
  if (allow.includes(origin)) return origin;
  if (/^http:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$/i.test(origin)) return origin;
  return allow[0] ?? "https://haterandrew.github.io";
}

function jsonResponse(body: unknown, init: ResponseInit, env: Env, request: Request): Response {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Access-Control-Allow-Origin", pickAllowedOrigin(env, request));
  headers.set("Vary", "Origin");
  return new Response(JSON.stringify(body), { ...init, headers });
}

function corsPreflight(env: Env, request: Request): Response {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": pickAllowedOrigin(env, request),
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    },
  });
}

// I2 (known limitation): the rate-limit and daily-budget counters use KV
// read-then-write, which is not atomic — N concurrent requests can each read the
// same count and all write count+1, letting a burst slip a little past the cap.
// For a personal app with a soft $1/day budget the overshoot is negligible. The
// atomic fix is a Durable Object (or the CF rate-limit binding): move the
// get/increment/put into a single-threaded DO method and call it here. Left as a
// documented follow-up rather than shipped unverified — a broken DO migration
// takes the live worker down on deploy, and it can't be exercised without
// `wrangler dev` + a deployed DO.
export async function checkRateLimit(env: Env, ip: string): Promise<{ ok: boolean; retryAfter?: number }> {
  // v3 S3: fail CLOSED when the KV binding is missing. This used to return
  // ok:true, so a KV outage, a renamed binding or a botched deploy silently
  // removed the rate limit and the daily budget at the same time — the two
  // controls that bound Anthropic spend — while the endpoint kept serving. An
  // unavailable limiter means the request cannot be shown to be within limits,
  // and for a paid upstream that has to read as "no".
  if (!env.KV) {
    console.error('KV binding unavailable — refusing request (rate limit cannot be enforced)');
    return { ok: false, retryAfter: 30 };
  }
  const limit = parseInt(env.RATE_LIMIT_PER_MIN, 10) || 20;
  const bucket = Math.floor(Date.now() / 60_000);
  const key = `rl:${ip}:${bucket}`;
  const raw = await env.KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= limit) return { ok: false, retryAfter: 60 - Math.floor((Date.now() % 60_000) / 1000) };
  await env.KV.put(key, String(count + 1), { expirationTtl: 120 });
  return { ok: true };
}

// Aligned with wrangler.toml DAILY_BUDGET_USD. Used only when the var is unset
// or non-numeric; a configured "0" now correctly disables spend (was impossible
// with `|| 2`, which also silently doubled a blank cap). (I4)
const DEFAULT_DAILY_BUDGET_USD = 1;

export async function checkDailyBudget(env: Env): Promise<{ ok: boolean; spent: number; cap: number }> {
  const parsed = parseFloat(env.DAILY_BUDGET_USD);
  const cap = Number.isFinite(parsed) ? parsed : DEFAULT_DAILY_BUDGET_USD;
  // v3 S3: fail closed for the same reason as checkRateLimit. Without KV the
  // spend counter cannot be read OR written, so every request would look like
  // the first one of the day and the cap would never bind.
  if (!env.KV) {
    console.error('KV binding unavailable — refusing request (daily budget cannot be enforced)');
    return { ok: false, spent: 0, cap };
  }
  const day = new Date().toISOString().slice(0, 10);
  const raw = await env.KV.get(`cost:${day}`);
  const spent = raw ? parseFloat(raw) : 0;
  return { ok: spent < cap, spent, cap };
}

export async function recordCost(env: Env, usdDelta: number): Promise<void> {
  if (!env.KV) return;
  const day = new Date().toISOString().slice(0, 10);
  const key = `cost:${day}`;
  const raw = await env.KV.get(key);
  const spent = raw ? parseFloat(raw) : 0;
  await env.KV.put(key, (spent + usdDelta).toFixed(4), { expirationTtl: 86400 * 2 });
}

// I1: per-model USD/MTok price table. Keyed by model-id prefix so dated
// variants (…-20250101) match. Budget accounting must fail loud on an unknown
// model rather than silently bill Sonnet rates for an Opus deployment.
interface ModelPricing {
  input: number;
  output: number;
  cacheWrite: number;
  cacheRead: number;
}
const MODEL_PRICING: Record<string, ModelPricing> = {
  // Sonnet 5 standard rate (intro $2/$10 runs through 2026-08-31; the budget
  // guard uses the durable rate so it over-counts, never under-counts).
  "claude-sonnet-5": { input: 3.0, output: 15.0, cacheWrite: 3.75, cacheRead: 0.3 },
  "claude-sonnet-4": { input: 3.0, output: 15.0, cacheWrite: 3.75, cacheRead: 0.3 },
  "claude-opus-4": { input: 15.0, output: 75.0, cacheWrite: 18.75, cacheRead: 1.5 },
  "claude-haiku-4": { input: 1.0, output: 5.0, cacheWrite: 1.25, cacheRead: 0.1 },
};
// code_execution bills container uptime separately (~$0.05/hour). We can't see
// wall-clock per request, so add a small per-invocation term when it ran.
const CODE_EXEC_COST_PER_CALL = 0.0005;

export function pricingFor(model: string): ModelPricing {
  const key = Object.keys(MODEL_PRICING).find(k => model.startsWith(k));
  if (!key) {
    throw new Error(`No price table entry for model "${model}" — add it to MODEL_PRICING before deploying.`);
  }
  return MODEL_PRICING[key];
}

export function estimateCost(usage: Anthropic.Beta.BetaUsage, model: string, codeExecCalls = 0): number {
  const p = pricingFor(model);
  const i = usage.input_tokens ?? 0;
  const o = usage.output_tokens ?? 0;
  const cw = usage.cache_creation_input_tokens ?? 0;
  const cr = usage.cache_read_input_tokens ?? 0;
  const tokenCost = ((i * p.input) + (o * p.output) + (cw * p.cacheWrite) + (cr * p.cacheRead)) / 1_000_000;
  return tokenCost + codeExecCalls * CODE_EXEC_COST_PER_CALL;
}

interface RunResult {
  answer: string;
  tools_used: string[];
  latency_ms: number;
  cost_usd: number;
}

async function runAgentLoop(
  client: Anthropic,
  model: string,
  body: AskRequest,
  cd: CachedData,
  // v3 S4: called with each turn's cost as soon as it is known. Returns false
  // when the daily cap has been reached, which stops the loop early.
  onTurnCost?: (usdDelta: number) => Promise<boolean>
): Promise<RunResult> {
  const start = Date.now();
  const toolsUsed: string[] = [];
  let totalCost = 0;
  let budgetStopped = false;

  const messages: Anthropic.Beta.BetaMessageParam[] = [];
  if (body.history && Array.isArray(body.history)) {
    // I3: cap per-turn history bytes so a client can't inflate token cost by
    // sending huge prior "turns" (the live question is already capped at 2000).
    const MAX_TURN_CHARS = 4000;
    for (const turn of body.history.slice(-8)) {
      if (turn.role !== "user" && turn.role !== "assistant") continue;
      if (typeof turn.content !== "string" || !turn.content.trim()) continue;
      messages.push({ role: turn.role, content: turn.content.slice(0, MAX_TURN_CHARS) });
    }
  }

  // Initial user turn: question text + container_upload referencing the dataset.
  const initialContent: Anthropic.Beta.BetaContentBlockParam[] = [
    { type: "text", text: body.question },
  ];
  if (cd.fileId) {
    initialContent.push({ type: "container_upload", file_id: cd.fileId });
  }
  messages.push({ role: "user", content: initialContent });

  const sys = systemPrompt({
    index: cd.index,
    generated: cd.data.generated,
    modelDescription: cd.data.model_description,
    dataMountPath: DATA_MOUNT_PATH,
  });

  const tools: Anthropic.Beta.BetaToolUnion[] = [...TOOLS, CODE_EXECUTION_TOOL];

  const MAX_TURNS = 8;
  for (let turn = 0; turn < MAX_TURNS; turn++) {
    const resp: Anthropic.Beta.BetaMessage = await client.beta.messages.create({
      model,
      max_tokens: 4000,
      system: [{ type: "text", text: sys, cache_control: { type: "ephemeral" } }],
      tools,
      output_config: { effort: "medium" },
      messages,
      betas: ["files-api-2025-04-14"],
    });

    // Track tool usage. Server-side tools (code_execution) emit server_tool_use blocks
    // with names like "bash_code_execution", "text_editor_code_execution". We collapse
    // those into a single "code_execution" entry for the response payload. Detect it
    // before costing so the container-time term is billed (I1).
    let sawCodeExec = false;
    for (const block of resp.content) {
      if (block.type === "server_tool_use") {
        const name = (block as { name?: string }).name ?? "";
        if (name.includes("code_execution")) sawCodeExec = true;
      }
    }
    const turnCost = estimateCost(resp.usage, model, sawCodeExec ? 1 : 0);
    totalCost += turnCost;
    if (sawCodeExec && !toolsUsed.includes("code_execution")) {
      toolsUsed.push("code_execution");
    }

    // v3 S4: bill and re-check the cap on every turn, not once at the end.
    // The budget used to be checked a single time before the loop and the spend
    // recorded once after it, via waitUntil — so one request could run all eight
    // turns unbilled, and concurrent requests each saw a pre-loop counter that
    // no in-flight request had yet updated. Recording inline and re-reading the
    // cap between turns bounds the overshoot to roughly one turn per concurrent
    // request instead of eight.
    if (onTurnCost) {
      const within = await onTurnCost(turnCost);
      if (!within) {
        budgetStopped = true;
        break;
      }
    }

    if (resp.stop_reason === "tool_use") {
      // Find user-side tool calls only — server-side tools (code_execution) are
      // already handled in-place by Anthropic's infrastructure.
      const toolUseBlocks = resp.content.filter(
        (b): b is Anthropic.Beta.BetaToolUseBlock => b.type === "tool_use"
      );
      messages.push({ role: "assistant", content: resp.content });
      const results: Anthropic.Beta.BetaToolResultBlockParam[] = toolUseBlocks.map((tu) => {
        toolsUsed.push(tu.name);
        const out = runTool(tu.name, tu.input, cd.data);
        return {
          type: "tool_result",
          tool_use_id: tu.id,
          content: JSON.stringify(out),
        };
      });
      messages.push({ role: "user", content: results });
      continue;
    }

    if (resp.stop_reason === "pause_turn") {
      // Server-side tool loop hit its 10-iteration cap. Re-send the assistant
      // content; the API resumes server-side execution automatically.
      messages.push({ role: "assistant", content: resp.content });
      continue;
    }

    if (resp.stop_reason === "end_turn" || resp.stop_reason === "max_tokens") {
      const text = resp.content
        .filter((b): b is Anthropic.Beta.BetaTextBlock => b.type === "text")
        .map((b) => b.text)
        .join("")
        .trim();
      return {
        answer: text || "(no answer returned)",
        tools_used: toolsUsed,
        latency_ms: Date.now() - start,
        cost_usd: +totalCost.toFixed(6),
      };
    }

    if (resp.stop_reason === "refusal") {
      return {
        answer: "I can't answer that one. Try a different question about the tournament data.",
        tools_used: toolsUsed,
        latency_ms: Date.now() - start,
        cost_usd: +totalCost.toFixed(6),
      };
    }

    return {
      answer: `(unexpected stop_reason: ${resp.stop_reason ?? "null"})`,
      tools_used: toolsUsed,
      latency_ms: Date.now() - start,
      cost_usd: +totalCost.toFixed(6),
    };
  }

  return {
    answer: budgetStopped
      ? "I ran out of the daily question budget partway through this one. Try again tomorrow."
      : "Sorry — I got stuck looking that up. Try rephrasing the question.",
    tools_used: toolsUsed,
    latency_ms: Date.now() - start,
    cost_usd: +totalCost.toFixed(6),
  };
}

// ── CCA tournament-list fetch proxy ────────────────────────────────────────
// chessaction.com started 403-blocking GitHub Actions' Azure IP ranges, which
// breaks the daily scraper in CI (a residential IP and Cloudflare's edge both
// still get 200). This route lets the GH Action fetch the tournament list
// THROUGH Cloudflare's edge instead of hitting the site directly. It replays
// the exact AJAX POST the scraper would have made and returns the upstream
// bytes verbatim, so the Python parser is unchanged. Gated by a shared secret
// (X-Proxy-Key) so it isn't an open proxy.
const CCA_TOURLIST_URL = "https://www.chessaction.com/ajaxFrontGetTourListNew.php";
const CCA_VENDOR_ID = "3";

/**
 * Constant-time string comparison (v3 S6).
 *
 * `!==` on a secret returns as soon as it hits a differing byte, so response
 * time leaks how many leading characters were correct and the key can be
 * recovered a character at a time. The XOR-accumulate form always walks the
 * full length. Comparing lengths first would reintroduce a leak, so the length
 * difference is folded into the accumulator instead.
 */
export function timingSafeEqual(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

async function proxyCcaTourList(env: Env, request: Request): Promise<Response> {
  const expected = env.CCA_PROXY_KEY;
  const provided = request.headers.get("X-Proxy-Key");
  // Require the secret to be configured AND matched. Fail closed.
  if (!expected || !provided || !timingSafeEqual(provided, expected)) {
    return new Response("Forbidden", { status: 403 });
  }

  try {
    const upstream = await fetch(CCA_TOURLIST_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent":
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        Accept: "text/html,*/*",
        Referer: "https://www.chessaction.com/",
      },
      body: `vendor_search=${CCA_VENDOR_ID}&length=-1`,
    });

    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        // Surface the upstream status to the caller for diagnostics.
        "X-Upstream-Status": String(upstream.status),
      },
    });
  } catch (e) {
    return new Response(`Upstream fetch failed: ${(e as Error).message}`, { status: 502 });
  }
}

// Browser-facing proxy for CCA public entry-list pages. The PWA's Audit tab
// cannot fetch chessaction.com directly (CSP connect-src + no CORS upstream),
// so it asks this route for the page. Unlike /cca-tourlist this is meant for
// the browser: CORS headers via pickAllowedOrigin, per-IP rate limiting, and
// no shared secret — the URL space is a strict template over an allowlisted
// event-name map (entrylist_codes.mjs), not an open proxy.
async function proxyCcaEntryList(env: Env, request: Request): Promise<Response> {
  const url = new URL(request.url);
  const event = url.searchParams.get("event") ?? "";
  const year = url.searchParams.get("year") ?? "";

  if (!/^20(2\d|3[0-5])$/.test(year)) {
    return jsonResponse({ error: "bad_year", message: "year must be 2020-2035" }, { status: 400 }, env, request);
  }
  const code = deriveEntryListCode(event);
  if (!code || !/^[A-Z]{1,6}$/.test(code)) {
    return jsonResponse({ error: "unknown_event", message: `cannot derive an entry-list code from "${event}"` }, { status: 400 }, env, request);
  }

  const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
  const rl = await checkRateLimit(env, ip);
  if (!rl.ok) {
    return jsonResponse(
      { error: "rate_limited", message: "Too many requests — wait a minute." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfter ?? 60) } },
      env,
      request
    );
  }

  try {
    const upstream = await fetch(entryListUrl(code, year), {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        Accept: "text/html,*/*",
        Referer: "https://www.chessaction.com/",
      },
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": pickAllowedOrigin(env, request),
        // Custom headers are invisible to cross-origin JS unless exposed.
        "Access-Control-Expose-Headers": "X-Entry-Code, X-Upstream-Status",
        Vary: "Origin",
        "X-Entry-Code": `CCA_${code}${year.slice(-2)}`,
        "X-Upstream-Status": String(upstream.status),
      },
    });
  } catch (e) {
    return jsonResponse(
      { error: "upstream_failed", message: (e as Error).message },
      { status: 502 },
      env,
      request
    );
  }
}

export default {
  // `ctx` is intentionally unused: cost is now recorded inline per turn (v3 S4)
  // rather than deferred through ctx.waitUntil after the loop finished.
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") return corsPreflight(env, request);

    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return jsonResponse({ ok: true, model: env.MODEL, file_id: cached?.fileId ?? null }, { status: 200 }, env, request);
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
