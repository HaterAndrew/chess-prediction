import { describe, expect, it } from "vitest";
import { acquireRegistrations, registrationTime } from "./registrations";

const stamp = (local: string) => `<span title="${local} UTC">${local}<br />(GMT+00:00)</span>`;
const row = (id: number, time: string) => ({ eventId: id, tourid: "123", createdAt: stamp(time),
  created_at: "2026-01-01 00:00:00", firstname: "PRIVATE", email: "private@example.test" });
function source(active: Record<string, unknown>[], withdrawn: Record<string, unknown>[], transform = (x: unknown) => x) {
  const calls: Record<string, string>[] = [];
  return { calls, request: async (path: string, fields: Record<string, string>, method: string) => {
    expect(path).toBe("ajaxRegistrationDataTable.php"); expect(method).toBe("POST");
    expect(fields.tournment).toBe("123"); expect(fields.reg_filter).toBe("all");
    const rows = fields.status === "active" ? active : withdrawn;
    calls.push(fields);
    return JSON.stringify(transform({ iTotalRecords: String(rows.length), iTotalDisplayRecords: rows.length,
      aaData: rows.slice(Number(fields.start), Number(fields.start) + Number(fields.length)) }));
  }};
}
const card = { family: "Example Open", year: 2026 };
const now = "2026-11-10T12:00:00.000Z";

describe("registration source aggregates", () => {
  it("uses the export-equivalent local registration display, without reconverting its inconsistent GMT label", () => {
    expect(registrationTime('<span title="2026-02-01 18:00:00 UTC">2026-02-01 12:00:00<br />(GMT-06:00)</span>'))
      .toBe("2026-02-01 12:00:00");
    expect(() => registrationTime(stamp("2026-02-30 12:00:00"))).toThrow("registration_time_invalid");
    expect(registrationTime('<span title="2026-02-01 18:00:00 UTC">2026-02-01 13:00:00<br />(GMT-06:00)</span>')).toBe("2026-02-01 13:00:00");
    expect(() => registrationTime('<span title="2026-02-01 12:00:00 UTC">2026-02-01 12:00:00<br />(GMT-15:00)</span>')).toThrow("registration_time_invalid");
  });
  it("matches exact floor bins across a subday boundary; retains no personal fields", async () => {
    const client = source([row(1, "2026-02-01 14:00:00"), row(2, "2026-02-02 13:00:00")], [row(3, "2026-01-31 12:00:00")]);
    const result = await acquireRegistrations(client, card, "123", now);
    expect(result).toMatchObject({ total: 3, active: 2, withdrawn: 1, ts_count: 3,
      first_reg: "2026-01-31 12:00:00", last_reg: "2026-02-02 13:00:00",
      daily: [{ T: 2, daily_regs: 1 }, { T: 0, daily_regs: 2 }],
      calendar_daily: [{ date: "2026-01-31", daily_regs: 1 }, { date: "2026-02-01", daily_regs: 1 }, { date: "2026-02-02", daily_regs: 1 }] });
    expect(JSON.stringify(result)).not.toMatch(/PRIVATE|example.test|firstname|email|eventId|created_at/);
    expect(client.calls).toHaveLength(4);
  });
  it("refuses positive registrations with no timestamps while allowing a zero-entry waiting report", async () => {
    await expect(acquireRegistrations(source([{ ...row(1, "2026-02-01 12:00:00"), createdAt: null }], []), card, "123", now))
      .rejects.toThrow("registration_timestamps_missing");
    expect(await acquireRegistrations(source([], []), card, "123", now)).toMatchObject({ total: 0, ts_count: 0, daily: [], calendar_daily: [] });
  });
  it("paginates completely, including withdrawals", async () => {
    const client = source(Array.from({ length: 1001 }, (_, i) => row(i + 1, "2026-02-01 12:00:00")), []);
    expect((await acquireRegistrations(client, card, "123", now)).total).toBe(1001);
    expect(client.calls.map(c => [c.status, c.start, c.length])).toEqual([
      ["active", "0", "1000"], ["active", "1000", "1000"], ["withdrawn", "0", "1000"],
      ["active", "0", "1"], ["withdrawn", "0", "1"]]);
  });
  it.each([
    ["wrong tournament", [ { ...row(1, "2026-02-01 12:00:00"), tourid: "999" } ], []],
    ["duplicate ID", [row(1, "2026-02-01 12:00:00")], [row(1, "2026-02-01 12:00:00")]],
    ["timestamp markup", [{ ...row(1, "2026-02-01 12:00:00"), createdAt: '<script>bad()</script>' }], []],
    ["future timestamp", [row(1, "2027-02-01 12:00:00")], []],
  ])("rejects %s", async (_, active, withdrawn) => {
    await expect(acquireRegistrations(source(active, withdrawn), card, "123", now)).rejects.toThrow();
  });
  it("refuses changes at final count fence and never exposes source exception data", async () => {
    const client = source([row(1, "2026-02-01 12:00:00")], []);
    const original = client.request;
    client.request = async (path, fields, method) => fields.length === "1"
      ? JSON.stringify({ iTotalRecords: 2, iTotalDisplayRecords: 2, aaData: [row(1, "2026-02-01 12:00:00")] })
      : original(path, fields, method);
    await expect(acquireRegistrations(client, card, "123", now)).rejects.toThrow("source_changed_during_read");
  });
});
