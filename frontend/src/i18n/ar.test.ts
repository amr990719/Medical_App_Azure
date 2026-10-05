import { describe, expect, it } from "vitest";
import { ar, t } from "./ar";

describe("t", () => {
  it("fills placeholders", () => {
    expect(t(ar.dashboard.greeting, { name: "أحمد" })).toBe("مرحباً د. أحمد");
  });

  it("leaves unknown placeholders visible", () => {
    expect(t("{a} {b}", { a: 1 })).toBe("1 {b}");
  });
});
