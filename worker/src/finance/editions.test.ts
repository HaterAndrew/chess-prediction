import { describe, expect, it } from "vitest";
import { matchTournament, normalizeFamily } from "./editions";

const legacy = "New York State Senior Championship With Young Adult Mi";
const source = "New York State Senior Championship (With Young Adult/Middle Age Section)";

describe("combined historical Senior source identity", () => {
  it.each([{ year: 2025, id: "3731" }, { year: 2026, id: "4182" }])("matches the exact combined source in $year", ({ year, id }) => {
    expect(matchTournament({ family: legacy, year }, [{ id, title: `${year} ${source}` }])).toBe(id);
  });
  it("keeps the separate Senior and Adult families distinct", () => {
    expect(normalizeFamily(source)).toBe(normalizeFamily(legacy));
    for (const family of ["New York State Senior Championship", "Saratoga Tournament Of-The-Ages Open"]) {
      expect(normalizeFamily(source)).not.toBe(normalizeFamily(family));
      expect(() => matchTournament({ family, year: 2026 }, [{ id: "4182", title: `2026 ${source}` }])).toThrow("unmapped_tournament");
    }
  });
  it("retains exact year, name and ambiguity fences", () => {
    expect(() => matchTournament({ family: legacy, year: 2027 }, [{ id: "4182", title: `2026 ${source}` }])).toThrow("unmapped_tournament");
    expect(() => matchTournament({ family: legacy, year: 2026 }, [{ id: "4182", title: `2026 ${source} Extra` }])).toThrow("unmapped_tournament");
    expect(() => matchTournament({ family: legacy, year: 2026 }, ["4182", "9999"].map(id => ({ id, title: `2026 ${source}` })))).toThrow("ambiguous_tournament");
  });
});
