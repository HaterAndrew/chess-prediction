import { afterEach, expect, it, vi } from "vitest";
import { ChessActionClient } from "./client";
afterEach(() => vi.restoreAllMocks());
it("reports a resumable job limit when its deadline ends during transport", async () => {
  let now = 1000; vi.spyOn(Date, "now").mockImplementation(() => now);
  const client = new ChessActionClient(async () => { now += 101; throw new Error("transport_aborted"); }, 42, 100);
  await expect(client.request("search.php")).rejects.toThrow("source_request_limit");
});
it("reports a resumable job limit when its deadline ends during body reading", async () => {
  let now = 1000; vi.spyOn(Date, "now").mockImplementation(() => now);
  const client = new ChessActionClient(async () => new Response(new ReadableStream({
    pull(controller) { now += 101; controller.error(new Error("body_aborted")); },
  })), 42, 100);
  await expect(client.request("search.php")).rejects.toThrow("source_request_limit");
});
it("keeps a genuine network failure distinct from the job deadline", async () => {
  const client = new ChessActionClient(async () => { throw new Error("offline"); });
  await expect(client.request("search.php")).rejects.toThrow("source_network_failed");
});
it("bounds the aggregate player-report payload across pages", async () => {
  const page = JSON.stringify({ recordsFiltered: 9000, data: Array.from({ length: 1000 }, () => ({ payload: "x".repeat(1000) })) });
  const client = new ChessActionClient(async () => new Response(page));
  await expect(client.playerRows("123")).rejects.toThrow("source_too_many_rows");
});
it("retains complete requested orders while discarding unrelated broad-query rows", async () => {
  const pages = [
    { recordsFiltered: "1001", data: Array.from({ length: 1000 }, (_, i) => ({ order_id: i === 999 ? "900" : "1", tournament: "2026 Example Open" })) },
    { recordsFiltered: "1001", data: [{ order_id: "900", tournament: "2026 Another Open" }] },
  ];
  const client = new ChessActionClient(async () => Response.json(pages.shift()));
  const rows = await client.playerRows("All", "Cash", ["900"]);
  expect(rows).toEqual([{ order_id: "900", tournament: "2026 Example Open" }, { order_id: "900", tournament: "2026 Another Open" }]);
});
it("processes a large broad-query prefix without retaining unrelated payloads", async () => {
  const page = JSON.stringify({ recordsFiltered: 9000, data: Array.from({ length: 1000 }, () => ({ order_id: "1", payload: "x".repeat(1000) })) });
  const client = new ChessActionClient(async () => new Response(page));
  expect(await client.playerRows("All", "Cash", ["900"])).toEqual([]);
});
