import { describe, expect, it } from "vitest";
import { sha256 } from "./types";
import { matchPublicRegistrations } from "./public-cohort";

describe("source/public registration identity", async () => {
  const first = { id: "101", uscf: "12345678", fide: "1234567" };
  it("uses unique federation IDs while allowing unrelated rows in a combined public list", async () => {
    expect(await matchPublicRegistrations([{ uscf_id: "12345678" }], [first, { id: "102", uscf: "87654321", fide: "" }])).toEqual(["101"]);
  });
  it("refuses ambiguous public IDs and repeated source identities", async () => {
    expect(await matchPublicRegistrations([{ uscf_id: "12345678" }], [first, { ...first, id: "102" }])).toBeNull();
    expect(await matchPublicRegistrations([{ uscf_id: "12345678" }, { uscf_id: "12345678" }], [first, { id: "102", uscf: "87654321", fide: "" }])).toBeNull();
  });
  it("uses a unique FIDE ID only when no valid USCF ID is present", async () => {
    expect(await matchPublicRegistrations([{ uscf_id: "", fide_id: "1234567" }], [first])).toEqual(["101"]);
    expect(await matchPublicRegistrations([{ uscf_id: "", fide_id: "" }], [first])).toBeNull();
    expect(await matchPublicRegistrations([{ uscf_id: "87654321", fide_id: "1234567" }], [first])).toBeNull();
  });
  it("matches an unrated registration only by a unique exact in-memory name digest", async () => {
    const name_hash = await sha256("synthetic player");
    const unrated = { id: "103", uscf: "", fide: "", name_hash };
    const source = { player_first_name: " Synthetic ", player_last_name: "Player", uscf_id: "", fide_id: "" };
    expect(await matchPublicRegistrations([source], [first, unrated])).toEqual(["103"]);
    expect(await matchPublicRegistrations([source], [unrated, { ...unrated, id: "104" }])).toBeNull();
    expect(await matchPublicRegistrations([{ ...source, player_last_name: "Other" }], [unrated])).toBeNull();
    expect(await matchPublicRegistrations([{ ...source, uscf_id: "87654321" }], [unrated])).toBeNull();
    expect(await matchPublicRegistrations([source, source], [unrated])).toBeNull();
    for (const invalid of [{uscf_id:"1234567"},{uscf_id:"unknown"},{fide_id:"12"},{fide_id:"pending"},{uscf_id:null},{fide_id:null},{uscf_id:undefined},{fide_id:undefined},{uscf_id:[]},{fide_id:[]}]) {
      expect(await matchPublicRegistrations([{...source,...invalid}], [unrated])).toBeNull();
    }
  });

  it("joins a newly assigned source ID only to an explicit unrated public row with a unique name", async () => {
    const name_hash = await sha256("synthetic player");
    const source = { uscf_id: "87654321", fide_id: "7654321", player_first_name: "Synthetic", player_last_name: "Player" };
    const pending = { id: "103", uscf: "", fide: "", name_hash, new_uscf: true as const };
    expect(await matchPublicRegistrations([source], [pending])).toEqual(["103"]);
    expect(await matchPublicRegistrations([source], [{ id: "103", uscf: "", fide: "", name_hash }])).toBeNull();
    expect(await matchPublicRegistrations([source], [{ ...pending, uscf: "11111111" }])).toBeNull();
    expect(await matchPublicRegistrations([source], [pending, { ...pending, id: "104" }])).toBeNull();
    expect(await matchPublicRegistrations([source], [pending, { id: "104", uscf: "11111111", fide: source.fide_id }])).toBeNull();
    expect(await matchPublicRegistrations([{ ...source, player_last_name: "Other" }], [pending])).toBeNull();
  });

});
