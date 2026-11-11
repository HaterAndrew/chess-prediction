import { describe, it, expect } from "vitest";
import { historicalForFamily, compareYears, type WebsiteData } from "./tools";
describe("transferred section provenance", () => {
  const data: WebsiteData = {generated:"2026-11-11",tournaments:[{family:"Example",year:2027,event_start:null,event_end:null,current_count:0,history_basis:"transferred_sections",history_transfer_inferred:true,history_note:"Prior sections; format differs.",historical:[{year:2026,count:12,family:"Example",source_family:"Predecessor",source_section:"Adult"}]}]};
  it("retains source section and inference in history and comparisons", () => {
    const result = historicalForFamily(data,{family:"Example"}) as any;
    expect(result.series[0]).toMatchObject({year:2026,count:12,source_family:"Predecessor",source_section:"Adult"});
    expect(result.history_transfer_inferred).toBe(true);
    expect(compareYears(data,{family:"Example",year_a:2026,year_b:2027})).toMatchObject({history_basis:"transferred_sections",history_note:"Prior sections; format differs.",year_a:{source_section:"Adult"}});
  });
  it("keeps a direct edition instead of overwriting it with proxy history", () => {
    const direct={family:"Example",year:2026,event_start:null,event_end:null,current_count:20};
    const result=historicalForFamily({...data,tournaments:[direct,...data.tournaments]},{family:"Example"}) as any;
    expect(result.series[0]).toEqual({year:2026,count:20});
    expect(result.history_basis).toBeUndefined();
  });
});
