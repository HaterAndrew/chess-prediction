// At the configured cadence: 72 * 12 collection writes + 72 health writes = 936/day.
export const FINANCE_WRITES_PER_RUN = 12;

/** Count attempted writes, including failures; never send an over-budget write. */
export class FinanceWriteBudget {
  readonly kv: KVNamespace;
  private used = 0;

  constructor(storage: KVNamespace, private readonly maximum = FINANCE_WRITES_PER_RUN) {
    if (!storage) throw new Error("finance_storage_missing");
    if (!Number.isInteger(maximum) || maximum < 1 || maximum > FINANCE_WRITES_PER_RUN) throw new Error("invalid_finance_write_budget");
    const put: KVNamespace["put"] = async (key, value, options) => {
      if (this.used >= this.maximum) throw new Error("finance_write_budget_exhausted");
      this.used++;
      return storage.put(key, value, options);
    };
    this.kv = new Proxy(storage, {
      get(target, key) {
        if (key === "put") return put;
        const value = Reflect.get(target, key, target);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
  }

  get remaining(): number { return this.maximum - this.used; }
}
