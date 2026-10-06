import { describe, expect, it } from "vitest";
import { formatDate, formatFileSize, formatMoney, formatNumber, formatRelativeTime } from "./format";

describe("formatMoney", () => {
  it("formats with the Arabic thousands separator, Western digits and the pound sign", () => {
    expect(formatMoney(3025)).toBe("3٬025 ج.م");
  });

  it("formats zero and small amounts", () => {
    expect(formatMoney(0)).toBe("0 ج.م");
    expect(formatMoney(750)).toBe("750 ج.م");
  });
});

describe("formatNumber", () => {
  it("uses the ar-EG grouping with Western digits", () => {
    expect(formatNumber(1234567)).toBe("1٬234٬567");
  });
});

describe("formatDate", () => {
  it("formats an ISO date with the ar-EG locale", () => {
    expect(formatDate("2026-10-03")).toBe("٣ أكتوبر ٢٠٢٦");
  });

  it("formats an ISO datetime in Cairo time", () => {
    // 23:30 UTC on Oct 2 is already Oct 3 in Cairo (UTC+3 in summer time).
    expect(formatDate("2026-10-02T23:30:00Z")).toBe("٣ أكتوبر ٢٠٢٦");
  });

  it("returns an empty string for missing values", () => {
    expect(formatDate(null)).toBe("");
  });
});

describe("formatRelativeTime", () => {
  it("says how long ago in Arabic with Western digits (PROMPT.md §43 example)", () => {
    const now = new Date("2026-10-05T12:00:00Z");
    expect(formatRelativeTime("2026-10-05T11:55:00Z", now)).toContain("5 دقائق");
  });

  it("uses hours and days for older values", () => {
    const now = new Date("2026-10-05T12:00:00Z");
    expect(formatRelativeTime("2026-10-05T09:00:00Z", now)).toContain("3 ساعات");
    expect(formatRelativeTime("2026-10-02T12:00:00Z", now)).toContain("3 أيام");
  });
});

describe("formatFileSize", () => {
  it("shows megabytes with one decimal and kilobytes below 1 MB", () => {
    expect(formatFileSize(1_572_864)).toBe("1.5 ميجابايت");
    expect(formatFileSize(8 * 1024 * 1024)).toBe("8 ميجابايت");
    expect(formatFileSize(2048)).toBe("2 كيلوبايت");
  });
});
