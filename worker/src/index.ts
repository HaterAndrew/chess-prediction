import Anthropic from "@anthropic-ai/sdk";
import { TOOLS, CODE_EXECUTION_TOOL, buildIndex, runTool, type WebsiteData } from "./tools";
import { systemPrompt } from "./prompts";

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

function pickAllowedOrigin(env: Env, request: Request): string {
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

async function checkRateLimit(env: Env, ip: string): Promise<{ ok: boolean; retryAfter?: number }> {
  if (!env.KV) return { ok: true };
  const limit = parseInt(env.RATE_LIMIT_PER_MIN, 10) || 20;
  const bucket = Math.floor(Date.now() / 60_000);
  const key = `rl:${ip}:${bucket}`;
  const raw = await env.KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= limit) return { ok: false, retryAfter: 60 - Math.floor((Date.now() % 60_000) / 1000) };
  await env.KV.put(key, String(count + 1), { expirationTtl: 120 });
  return { ok: true };
}

async function checkDailyBudget(env: Env): Promise<{ ok: boolean; spent: number; cap: number }> {
  const cap = parseFloat(env.DAILY_BUDGET_USD) || 2;
  if (!env.KV) return { ok: true, spent: 0, cap };
  const day = new Date().toISOString().slice(0, 10);
  const raw = await env.KV.get(`cost:${day}`);
  const spent = raw ? parseFloat(raw) : 0;
  return { ok: spent < cap, spent, cap };
}

async function recordCost(env: Env, usdDelta: number): Promise<void> {
  if (!env.KV) return;
  const day = new Date().toISOString().slice(0, 10);
  const key = `cost:${day}`;
  const raw = await env.KV.get(key);
  const spent = raw ? parseFloat(raw) : 0;
  await env.KV.put(key, (spent + usdDelta).toFixed(4), { expirationTtl: 86400 * 2 });
}

const PRICE_INPUT = 3.0;
const PRICE_OUTPUT = 15.0;
const PRICE_CACHE_WRITE = 3.75;
const PRICE_CACHE_READ = 0.3;

function estimateCost(usage: Anthropic.Beta.BetaUsage): number {
  const i = usage.input_tokens ?? 0;
  const o = usage.output_tokens ?? 0;
  const cw = usage.cache_creation_input_tokens ?? 0;
  const cr = usage.cache_read_input_tokens ?? 0;
  return ((i * PRICE_INPUT) + (o * PRICE_OUTPUT) + (cw * PRICE_CACHE_WRITE) + (cr * PRICE_CACHE_READ)) / 1_000_000;
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
  cd: CachedData
): Promise<RunResult> {
  const start = Date.now();
  const toolsUsed: string[] = [];
  let totalCost = 0;

  const messages: Anthropic.Beta.BetaMessageParam[] = [];
  if (body.history && Array.isArray(body.history)) {
    for (const turn of body.history.slice(-8)) {
      if (turn.role !== "user" && turn.role !== "assistant") continue;
      if (typeof turn.content !== "string" || !turn.content.trim()) continue;
      messages.push({ role: turn.role, content: turn.content });
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

    totalCost += estimateCost(resp.usage);

    // Track tool usage. Server-side tools (code_execution) emit server_tool_use blocks
    // with names like "bash_code_execution", "text_editor_code_execution". We collapse
    // those into a single "code_execution" entry for the response payload.
    let sawCodeExec = false;
    for (const block of resp.content) {
      if (block.type === "server_tool_use") {
        const name = (block as { name?: string }).name ?? "";
        if (name.includes("code_execution")) sawCodeExec = true;
      }
    }
    if (sawCodeExec && !toolsUsed.includes("code_execution")) {
      toolsUsed.push("code_execution");
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
    answer: "Sorry — I got stuck looking that up. Try rephrasing the question.",
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

async function proxyCcaTourList(env: Env, request: Request): Promise<Response> {
  const expected = env.CCA_PROXY_KEY;
  const provided = request.headers.get("X-Proxy-Key");
  // Require the secret to be configured AND matched. Fail closed.
  if (!expected || provided !== expected) {
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

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") return corsPreflight(env, request);

    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return jsonResponse({ ok: true, model: env.MODEL, file_id: cached?.fileId ?? null }, { status: 200 }, env, request);
    }
    if (url.pathname === "/cca-tourlist") {
      return proxyCcaTourList(env, request);
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
      const result = await runAgentLoop(client, env.MODEL, body, cd);
      ctx.waitUntil(recordCost(env, result.cost_usd));
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
