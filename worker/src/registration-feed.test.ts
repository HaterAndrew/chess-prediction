import { describe, expect, it, vi } from "vitest";
import { handleRegistrationFeed } from "./registration-feed";
import type { Env } from "./env";
const request = (key?: string, method = "GET") => new Request("https://chessentries.com/registration-feed?tid=999&url=https://evil.test", {
  method, headers: key ? { "X-Proxy-Key": key } : {} });
const asset = { tournaments: [{ family: "Example", year: 2026, status: "live", event_start: "2026-12-01", private: "not_forwarded" }] };
function setup() {
  const registrations = vi.fn().mockResolvedValue({ version: 1, records: [] });
  const fetch = vi.fn().mockResolvedValue(Response.json(asset));
  return { registrations, fetch, env: { CCA_PROXY_KEY: "synthetic-proxy-key", FINANCE: { registrations }, ASSETS: { fetch } } as unknown as Env };
}
describe("private aggregate feed boundary", () => {
  it.each([undefined, "", "wrong"])("fails closed for %s without reading assets or private RPC", async key => {
    const x = setup();
    expect((await handleRegistrationFeed(x.env, request(key))).status).toBe(403);
    expect(x.fetch).not.toHaveBeenCalled(); expect(x.registrations).not.toHaveBeenCalled();
  });
  it("requires configured secret and private binding, and refuses mutation methods", async () => {
    const x = setup();
    expect((await handleRegistrationFeed({ ...x.env, CCA_PROXY_KEY: undefined }, request("synthetic-proxy-key"))).status).toBe(403);
    expect((await handleRegistrationFeed({ ...x.env, FINANCE: undefined }, request("synthetic-proxy-key"))).status).toBe(503);
    expect((await handleRegistrationFeed(x.env, request("synthetic-proxy-key", "POST"))).status).toBe(405);
  });
  it("uses server asset cards, ignores query selectors, sets no-store and has no storage writes", async () => {
    const x = setup(); const response = await handleRegistrationFeed(x.env, request("synthetic-proxy-key"));
    expect(response.status).toBe(200); expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(x.registrations).toHaveBeenCalledWith([{ family: "Example", year: 2026, status: "live", event_start: "2026-12-01", event_end: undefined }]);
    expect(x.fetch.mock.calls[0][0].pathname).toBe("/data/website_data.json");
  });
  it("does not forward stale assets or private source error details", async () => {
    const x = setup();x.fetch.mockResolvedValueOnce(Response.json({ ...asset, is_stale: true }));
    expect((await handleRegistrationFeed(x.env, request("synthetic-proxy-key"))).status).toBe(502);
    expect(x.registrations).not.toHaveBeenCalled();
    x.registrations.mockRejectedValueOnce(new Error("PRIVATE DETAILS"));
    expect(await (await handleRegistrationFeed(x.env, request("synthetic-proxy-key"))).json()).toEqual({ error: "data_unavailable" });
  });
});
