import { describe, expect, it } from "vitest";
import { ChessActionClient } from "./client";
describe("read-only source calendar boundary", () => {
  it("requests only the selected existing event by GET", async () => {
    let called = 0;
    const source = new ChessActionClient(async (url, init) => {
      called++; const target = new URL(url);
      expect(target.origin).toBe("https://chessaction.com"); expect(target.pathname).toBe("/admin/add_edit_tour.php");
      expect(target.search).toBe("?tid=4912"); expect(init?.method).toBe("GET"); expect(init?.body).toBeUndefined();
      return new Response("synthetic calendar");
    });
    expect(await source.eventSettings("4912")).toBe("synthetic calendar"); expect(called).toBe(1);
    for (const [fields, method] of [[{ tid: "4912" }, "POST"], [{ tid: "4912", save: "1" }, "GET"], [{ tid: "4912&save=1" }, "GET"]] as const) {
      await expect(source.request("add_edit_tour.php", fields, method)).rejects.toThrow("source_destination_refused");
    }
    expect(called).toBe(1);
  });
});

it.each([
  'https://attacker.invalid/collect',
  '/admin/add_edit_tour.php?tid=4912&save=1',
  '/admin/remove_tour.php?tid=4912',
])("refuses hostile calendar redirects before forwarding the session: %s", async location => {
  const calls: string[] = [];
  const source = new ChessActionClient(async (url, init) => {
    calls.push(url);
    if (new URL(url).pathname === '/admin/search.php') return new Response("Continental Chess Association<select id='tournments'></select>");
    expect(new Headers(init?.headers).get('Cookie')).toBe('session=synthetic-private');
    return new Response(null, { status: 307, headers: { Location: location } });
  });
  await source.resume('session=synthetic-private');
  await expect(source.eventSettings('4912')).rejects.toThrow('source_destination_refused');
  expect(calls).toHaveLength(2);
  expect(calls.every(url => new URL(url).origin === 'https://chessaction.com')).toBe(true);
});
