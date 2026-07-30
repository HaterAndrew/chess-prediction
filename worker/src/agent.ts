// Data cache + the model agent loop (index.ts, verbatim; W1).
import Anthropic from "@anthropic-ai/sdk";

import type { AskRequest, Env } from "./env";
import { estimateCost } from "./limits";
import { systemPrompt } from "./prompts";
import { TOOLS, CODE_EXECUTION_TOOL, buildIndex, runTool, type WebsiteData } from "./tools";

export interface CachedData {
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

// index.ts's /health route used to read the module-level cache directly;
// the cache stays module-private here, so expose the one field it needs.
export function cachedFileId(): string | null {
  return cached?.fileId ?? null;
}

export async function loadData(env: Env, client: Anthropic): Promise<CachedData> {
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

interface RunResult {
  answer: string;
  tools_used: string[];
  latency_ms: number;
  cost_usd: number;
}

export async function runAgentLoop(
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
