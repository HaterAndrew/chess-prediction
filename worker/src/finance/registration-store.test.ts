import { describe, expect, it } from "vitest";
import { registrationKey, registrationRecords, registrationTargets, registrationFeedRecords } from "./registration-store";
import { acquireRegistrations } from "./registrations";
const now = Date.parse("2026-11-10T12:00:00Z");
const card = { family: "Example Open", year: 2026, status: "live", event_start: "2026-11-14" };
async function record() {
  const data = await acquireRegistrations({ request: async (_path, fields) => {
    const rows = fields.status === "active" ? [{ eventId: "1", tourid: "123", createdAt: '<span title="2026-11-01 12:00:00 UTC">2026-11-01 12:00:00<br />(GMT+00:00)</span>' }] : [];
    return JSON.stringify({ aaData: rows, iTotalRecords: rows.length, iTotalDisplayRecords: rows.length });
  } }, card, "123", new Date(now).toISOString());
  return { ok: true, reason: null, attempted_at: new Date(now).toISOString(), data };
}
function storage(values: Map<string, string>) {
  return { get: async (keys: string | string[]) => { if (!Array.isArray(keys)) return values.get(keys) ?? null; expect(keys.length).toBeLessThanOrEqual(100);return new Map(keys.map(k => [k, values.get(k) ?? null])); } } as unknown as KVNamespace;
}
describe("registration cache/RPC projection", () => {
  it("observes only the private policy number while keeping the returned record closed", async () => {
    const x = { ...await record(), source_policy_version: 1, source_rows: ["PRIVATE ROW"] };
    const observed: Array<[string, number | null]> = [];
    const result = await registrationRecords(storage(new Map([[registrationKey(card), JSON.stringify(x)]])), [card], now,
      (key, version) => observed.push([key, version]));
    expect(observed).toEqual([[registrationKey(card), 1]]);
    expect(JSON.stringify(result)).not.toMatch(/source_policy_version|PRIVATE|source_rows/);
  });
  it("does not treat a local observer failure as corrupt source data", async () => {
    await expect(registrationRecords(storage(new Map([[registrationKey(card), JSON.stringify(await record())]])), [card], now,
      () => { throw new Error("local_observer_failed"); })).rejects.toThrow("local_observer_failed");
  });
  it("does not pass arbitrary policy contents to the scheduler", async () => {
    const x = { ...await record(), source_policy_version: { password: "PRIVATE" } };
    const observed: Array<number | null> = [];
    const result = await registrationRecords(storage(new Map([[registrationKey(card), JSON.stringify(x)]])), [card], now,
      (_key, version) => observed.push(version));
    expect(observed).toEqual([null]);
    expect(JSON.stringify(result)).not.toMatch(/source_policy_version|PRIVATE|password/);
  });
  it("ignores extra envelope fields and projects only closed aggregate fields", async () => {
    const x = { ...await record(), password: "PRIVATE ENVELOPE", source_rows: ["PRIVATE ROW"] };
    const values = new Map([[registrationKey(card), JSON.stringify(x)]]);
    const result = await registrationRecords(storage(values), [card], now);
    expect(result[0].ok).toBe(true); expect(result[0].data?.total).toBe(1);
    expect(JSON.stringify(result)).not.toMatch(/PRIVATE|password|source_rows/);
  });
  it.each([
    (x: Awaited<ReturnType<typeof record>>) => Object.assign(x.data, { email: "PRIVATE DATA" }),
    (x: Awaited<ReturnType<typeof record>>) => Object.assign(x.data.daily[0], { name: "PRIVATE DATA" }),
    (x: Awaited<ReturnType<typeof record>>) => Object.assign(x, { attempted_at: "2026-02-30T12:00:00.000Z" }),
    (x: Awaited<ReturnType<typeof record>>) => Object.assign(x.data, { source_as_of: "2027-01-01T12:00:00.000Z" }),
    (x: Awaited<ReturnType<typeof record>>) => Object.assign(x.data, { family: "Another Open" }),
    (x: Awaited<ReturnType<typeof record>>) => Object.assign(x.data, { total: 99 }),
  ])("refuses damaged or expanded aggregate schemas without leaking arbitrary contents", async mutate => {
    const x = await record(); mutate(x);
    const result = await registrationRecords(storage(new Map([[registrationKey(card), JSON.stringify(x)]])), [card], now);
    expect(result[0]).toMatchObject({ ok: false, reason: "registration_cache_invalid", data: null });
    expect(JSON.stringify(result)).not.toMatch(/PRIVATE/);
  });
  it("preserves a newer edition failure over an older global failure", async () => {
    const x = { ...await record(), ok: false, reason: "unmapped_tournament" };
    x.attempted_at = new Date(now - 3_600_000).toISOString();
    x.data.source_as_of = new Date(now - 3 * 3_600_000).toISOString();
    const values = new Map([[registrationKey(card), JSON.stringify(x)], ["registration_collector:status", JSON.stringify({
      attempted_at: new Date(now - 2 * 3_600_000).toISOString(), ok: false, reason: "source_login_expired" })]]);
    expect((await registrationFeedRecords(storage(values), [card], now))[0].reason).toBe("unmapped_tournament");
    values.set("registration_collector:status", JSON.stringify({ attempted_at: new Date(now).toISOString(), ok: false, reason: "source_login_expired" }));
    expect((await registrationFeedRecords(storage(values), [card], now))[0].reason).toBe("source_login_expired");
  });
  it("bounds eligible editions and rejects duplicate ownership", () => {
    expect(() => registrationTargets([card, card], now)).toThrow();
    expect(() => registrationTargets(Array.from({ length: 201 }, (_, i) => ({ ...card, family: `Example ${i}` })), now)).toThrow();
    expect(registrationTargets([{ ...card, year: 2023 }], now)).toEqual([]);
  });
});
