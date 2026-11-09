import { expect, it } from "vitest";
import { cents } from "./types";
it.each(["1,23", "1$2", "1,,234", "12,34.56", "$$12", "-1", "1.234", "1e3"])("rejects malformed money %s", value => {
  expect(() => cents(value)).toThrow("invalid_money");
});
it.each([["$1,234.56", 123456], ["1234.56", 123456], [" $12.50 ", 1250], ["0", 0]])("accepts verified USD formatting %s", (value, expected) => {
  expect(cents(value)).toBe(expected);
});
