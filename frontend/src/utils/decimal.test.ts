import { describe, expect, it } from "vitest";
import { formatDecimal, formatUsd, isNegativeDecimal, isPositiveDecimal } from "./decimal";

describe("decimal display helpers", () => {
  it("formats large values without converting them to floating point", () => {
    expect(formatDecimal("9007199254740993.125")).toBe("9,007,199,254,740,993.13");
  });

  it("rounds across the integer boundary and normalizes negative zero", () => {
    expect(formatDecimal("999.999")).toBe("1,000.00");
    expect(formatDecimal("-0.004")).toBe("0.00");
  });

  it("compares signed decimal strings without numeric coercion", () => {
    expect(isNegativeDecimal("-0.01")).toBe(true);
    expect(isNegativeDecimal("-0.00")).toBe(false);
    expect(isPositiveDecimal("0.01")).toBe(true);
    expect(isPositiveDecimal("0.00")).toBe(false);
  });

  it("places a negative currency sign before the symbol", () => {
    expect(formatUsd("-0.06")).toBe("-$0.06");
    expect(formatUsd("200")).toBe("$200.00");
  });
});
