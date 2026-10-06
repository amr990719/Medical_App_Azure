import { describe, expect, it } from "vitest";
import { parseNationalId } from "./nationalId";

const today = new Date("2026-10-06T12:00:00Z");

describe("parseNationalId (UX mirror of PROMPT.md §13)", () => {
  it("derives birth year and gender from a valid ID", () => {
    expect(parseNationalId("28506150101234", today)).toEqual({ birthYear: 1985, gender: "MALE" });
    expect(parseNationalId("30103150101242", today)).toEqual({ birthYear: 2001, gender: "FEMALE" });
  });

  it("accepts Eastern Arabic digits", () => {
    expect(parseNationalId("٢٨٥٠٦١٥٠١٠١٢٣٤", today)?.birthYear).toBe(1985);
  });

  it("returns null for incomplete, bad century, impossible or future dates", () => {
    expect(parseNationalId("2850615010123", today)).toBeNull();
    expect(parseNationalId("18506150101234", today)).toBeNull();
    expect(parseNationalId("28502300101234", today)).toBeNull();
    expect(parseNationalId("33012010101234", today)).toBeNull();
  });
});
