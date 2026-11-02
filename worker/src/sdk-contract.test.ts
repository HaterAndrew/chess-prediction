// Exercise the real SDK serializer/parser without a network call or API key.
import Anthropic from "@anthropic-ai/sdk";
import { describe, expect, it } from "vitest";
import { loadData, runAgentLoop, type CachedData } from "./agent";
import type { Env } from "./env";

function message(content: unknown[], stop = "end_turn") {
  return Response.json({
    id: "msg_contract", type: "message", role: "assistant",
    model: "claude-sonnet-5-5", content, stop_reason: stop, stop_sequence: null,
    usage: { input_tokens: 10, output_tokens: 2 },
  });
}

const cached: CachedData = {
  data: { generated: "2026-11-02", tournaments: [] }, index: "",
  fetchedAt: 0, fileId: null, fileUploadedAt: 0,
};

describe("Anthropic SDK contract", () => {
  it("serializes beta requests and continues a tool turn", async () => {
    const requests: Array<Record<string, unknown>> = [];
    const client = new Anthropic({
      apiKey: "synthetic-test-key", maxRetries: 0,
      fetch: async (input, init) => {
        const request = new Request(input, init);
        expect(new URL(request.url).pathname).toBe("/v1/messages");
        expect(request.headers.get("anthropic-beta")).toContain("server-side-fallback-2026-07-01");
        requests.push(await request.json() as Record<string, unknown>);
        return requests.length === 1
          ? message([{ type: "tool_use", id: "tool_contract", name: "search_tournaments", input: {} }], "tool_use")
          : message([{ type: "text", text: "No tournaments match." }]);
      },
    });
    const result = await runAgentLoop(client, "claude-sonnet-5-5", { question: "List tournaments" }, cached);
    expect(result.answer).toBe("No tournaments match.");
    expect(result.tools_used).toContain("search_tournaments");
    expect(requests[0]).toMatchObject({ output_config: { effort: "medium" }, fallbacks: "default" });
    const turns = requests[1].messages as Array<{ role: string; content: unknown }>;
    expect(turns.at(-1)).toMatchObject({ role: "user", content: [{ type: "tool_result", tool_use_id: "tool_contract" }] });
    expect(result.cost_usd).toBeGreaterThan(0);
  });

  it("propagates an API error instead of returning an answer", async () => {
    const requests: string[] = [];
    const client = new Anthropic({
      apiKey: "synthetic-test-key", maxRetries: 0,
      fetch: async (input, init) => {
        requests.push(new URL(new Request(input, init).url).pathname);
        return Response.json({ type: "error", error: { type: "overloaded_error", message: "Unavailable" } }, { status: 503 });
      },
    });
    await expect(runAgentLoop(client, "claude-sonnet-5-5", { question: "List tournaments" }, cached))
      .rejects.toMatchObject({ status: 503, message: expect.stringContaining("Unavailable") });
    expect(requests).toEqual(["/v1/messages"]);
  });

  it("uploads the asset dataset as a multipart file", async () => {
    const client = new Anthropic({
      apiKey: "synthetic-test-key", maxRetries: 0,
      fetch: async (input, init) => {
        const request = new Request(input, init);
        expect(new URL(request.url).pathname).toBe("/v1/files");
        const form = await request.formData();
        const file = form.get("file") as File;
        expect(file.name).toBe("website_data.json");
        expect(JSON.parse(await file.text())).toEqual(cached.data);
        return Response.json({ id: "file_contract", type: "file", filename: file.name, mime_type: "application/json", size_bytes: file.size, created_at: "2026-11-02T00:00:00Z", downloadable: true });
      },
    });
    const env = { ASSETS: { fetch: async () => Response.json(cached.data) } } as unknown as Env;
    expect((await loadData(env, client)).fileId).toBe("file_contract");
  });
});
