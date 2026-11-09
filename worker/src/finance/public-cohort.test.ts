import { describe, expect, it } from "vitest";
import { matchPublicRegistrations } from "./public-cohort";

describe("source/public registration identity", () => {
  const first = { id: "101", uscf: "12345678", fide: "1234567" };
  it("uses unique federation IDs while allowing unrelated rows in a combined public list", () => {
    expect(matchPublicRegistrations([{ uscf_id: "12345678" }], [first, { id: "102", uscf: "87654321", fide: "" }])).toEqual(["101"]);
  });
  it("refuses ambiguous public IDs and repeated source identities", () => {
    expect(matchPublicRegistrations([{ uscf_id: "12345678" }], [first, { ...first, id: "102" }])).toBeNull();
    expect(matchPublicRegistrations([{ uscf_id: "12345678" }, { uscf_id: "12345678" }], [first, { id: "102", uscf: "87654321", fide: "" }])).toBeNull();
  });
  it("uses a unique FIDE ID only when no valid USCF ID is present", () => {
    expect(matchPublicRegistrations([{ uscf_id: "", fide_id: "1234567" }], [first])).toEqual(["101"]);
    expect(matchPublicRegistrations([{ uscf_id: "", fide_id: "" }], [first])).toBeNull();
    expect(matchPublicRegistrations([{ uscf_id: "87654321", fide_id: "1234567" }], [first])).toBeNull();
  });
});
