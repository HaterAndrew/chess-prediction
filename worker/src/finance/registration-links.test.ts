import { describe, expect, it } from "vitest";
import { acquireRegistrationLinks, matchRegistrationLinks } from "./registration-links";

const publicRows = [{ id: "101", uscf: "87654321", fide: "" }, { id: "102", uscf: "22222222", fide: "" }];
const source = [{ order_id: "1", section: "Open", uscf_id: "12345678", fide_id: "" },
  { order_id: "2", section: "Open", uscf_id: "22222222", fide_id: "" }];
const links = [{ id: "101", order_id: "1", section: "Open" }, { id: "102", order_id: "2", section: "Open" }];

describe("native/public registration references", () => {
  it("repairs stale profile fields only through an exact unique order/section reference", async () => {
    expect(await matchRegistrationLinks(source, links, publicRows)).toEqual(["101", "102"]);
    expect(await matchRegistrationLinks(source, [{ ...links[0], order_id: "99" }, links[1]], publicRows)).toBeNull();
    expect(await matchRegistrationLinks(source, [{ ...links[0], section: "Other" }, links[1]], publicRows)).toBeNull();
  });
  it("requires a complete bijection with the actual public registration IDs", async () => {
    expect(await matchRegistrationLinks(source, links.slice(0, 1), publicRows)).toBeNull();
    expect(await matchRegistrationLinks(source, [{ ...links[0], id: "999" }, links[1]], publicRows)).toBeNull();
    expect(await matchRegistrationLinks(source, [links[0], { ...links[1], id: "101" }], publicRows)).toBeNull();
  });
  it("rejects ambiguous orders and repeated registration ownership", async () => {
    expect(await matchRegistrationLinks(source, [links[0], { ...links[1], order_id: "1" }], publicRows)).toBeNull();
    expect(await matchRegistrationLinks([source[0], source[0]], links, publicRows)).toBeNull();
  });
  it("collects bounded references using the existing source fences without retaining private fields", async () => {
    let calls = 0;
    const client = { request: async (_path: string, fields: Record<string, string>) => {
      calls++;
      const rows = fields.status === "active" ? [{ eventId: "101", tourid: "123", order_id: "1", section_menu_name: "Open",
        createdAt: '<span title="2026-11-01 12:00:00 UTC">2026-11-01 12:00:00<br />(GMT+00:00)</span>',
        firstname: "PRIVATE", email: "private@example.test" }] : [];
      return JSON.stringify({ iTotalRecords: rows.length, iTotalDisplayRecords: rows.length, aaData: rows });
    }};
    const result = await acquireRegistrationLinks(client, { family: "Example Open", year: 2026 }, "123", "2026-11-11T12:00:00.000Z");
    expect(result).toEqual([links[0]]);
    expect(calls).toBe(4);
    expect(JSON.stringify(result)).not.toMatch(/PRIVATE|email|firstname/);
  });
});
