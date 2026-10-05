import { describe, expect, it } from "vitest";
import { digitsOnly, normalizeDigits, toArabicDigits } from "./digits";

describe("normalizeDigits", () => {
  it("converts Eastern Arabic digits to Western", () => {
    expect(normalizeDigits("٠١٢")).toBe("012");
    expect(normalizeDigits("٢٩٥٠١٢٣٠١٠١٢٣٤")).toBe("29501230101234");
  });

  it("converts Persian digits too", () => {
    expect(normalizeDigits("۰۱۲۳۴۵۶۷۸۹")).toBe("0123456789");
  });

  it("keeps other characters untouched", () => {
    expect(normalizeDigits("عام ٢٠٢٦ - 2026")).toBe("عام 2026 - 2026");
  });
});

describe("digitsOnly", () => {
  it("normalizes then strips everything that is not a digit", () => {
    expect(digitsOnly("٢٩٥ ٠١-23a")).toBe("29501" + "23");
  });

  it("never drops Arabic digits", () => {
    expect(digitsOnly("٩")).toBe("9");
  });
});

describe("toArabicDigits", () => {
  it("converts Western digits to Eastern Arabic", () => {
    expect(toArabicDigits("2026")).toBe("٢٠٢٦");
  });
});
