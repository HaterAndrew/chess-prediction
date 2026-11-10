import { describe, expect, it } from "vitest";
import { isRegistrationTick, needsFinalCapture } from "./registration-collect";
const card = { family: "Example Open", year: 2026, status: "complete", event_start: "2026-11-07", event_end: "2026-11-09" };
describe("registration final-capture scheduling", () => {
  it("does not wait a week after a live report becomes a completed event", () => {
    expect(needsFinalCapture(card, "2026-11-09T23:40:00.000Z", Date.parse("2026-11-10T15:00:00Z"))).toBe(true);
    expect(needsFinalCapture(card, "2026-11-10T14:40:00.000Z", Date.parse("2026-11-10T15:00:00Z"))).toBe(false);
  });
  it("waits for the final local calendar day and keeps live events on their daily rule", () => {
    expect(needsFinalCapture(card, "2026-11-09T23:40:00.000Z", Date.parse("2026-11-10T13:00:00Z"))).toBe(false);
    expect(needsFinalCapture({ ...card, status: "live" }, undefined, Date.parse("2026-11-10T15:00:00Z"))).toBe(false);
    expect(needsFinalCapture({ ...card, event_end: "invalid" }, undefined, Date.parse("2026-11-10T15:00:00Z"))).toBe(false);
  });
  it("uses the scheduled slot, not the arrival time", () => {
    expect(isRegistrationTick(Date.parse("2026-11-10T14:40:00Z"))).toBe(true);
    expect(isRegistrationTick(Date.parse("2026-11-10T14:20:00Z"))).toBe(false);
  });
});
