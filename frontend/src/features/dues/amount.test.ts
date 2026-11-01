import { describe, expect, it } from "vitest";
import { parseAmountInput } from "./amount";

describe("parseAmountInput (UX only; the server validates again)", () => {
  it.each([
    ["250", "250"],
    ["٢٥٠", "250"],
    ["١٢٥٫٧٥", "125.75"],
    [" 40.5 ", "40.5"],
    ["0.01", "0.01"],
  ])("accepts %s as %s", (raw, expected) => {
    expect(parseAmountInput(raw)).toBe(expected);
  });

  it.each(["", "0", "0.00", "-5", "1,000", "1e3", "12.345", "abc", "123456789"])("refuses %s", (raw) => {
    expect(parseAmountInput(raw)).toBeNull();
  });
});
