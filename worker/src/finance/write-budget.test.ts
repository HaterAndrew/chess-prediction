import { describe, expect, it } from "vitest";
import { FinanceWriteBudget } from "./write-budget";

describe("finance write allowance", () => {
  it("counts failed attempts and stops the thirteenth underlying write", async () => {
    let writes = 0;
    const kv = { put: async () => { writes++; throw Error("storage_offline"); } } as unknown as KVNamespace;
    const budget = new FinanceWriteBudget(kv);
    for (let i = 0; i < 12; i++) await expect(budget.kv.put(`key${i}`, "value")).rejects.toThrow("storage_offline");
    await expect(budget.kv.put("collector:status", "failure")).rejects.toThrow("finance_write_budget_exhausted");
    await expect(budget.kv.put("collector:status", "outer failure")).rejects.toThrow("finance_write_budget_exhausted");
    expect(writes).toBe(12); expect(budget.remaining).toBe(0);
  });
  it("binds host methods correctly and leaves reads available after writes are exhausted", async () => {
    const store = { marker: "synthetic", get() { return Promise.resolve(this.marker); }, put: async () => {} };
    const budget = new FinanceWriteBudget(store as unknown as KVNamespace, 1);
    await budget.kv.put("key", "value");
    expect(await budget.kv.get("key")).toBe("synthetic");
    await expect(budget.kv.put("key", "value")).rejects.toThrow("finance_write_budget_exhausted");
  });
});
