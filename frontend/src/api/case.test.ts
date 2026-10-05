import { describe, expect, it } from "vitest";
import { toCamel, toSnake } from "./case";

describe("toCamel", () => {
  it("camelizes snake_case keys deeply, arrays included", () => {
    expect(
      toCamel({ fiscal_year: 2026, beneficiaries: [{ full_name: "x", birth_year: null }] }),
    ).toEqual({ fiscalYear: 2026, beneficiaries: [{ fullName: "x", birthYear: null }] });
  });

  it("leaves data keys (enum values, numbers) untouched", () => {
    expect(toCamel({ kinships: { SON_MINOR: { base_rule: "child" } }, by_step: { "1": [] } })).toEqual({
      kinships: { SON_MINOR: { baseRule: "child" } },
      byStep: { "1": [] },
    });
  });

  it("never touches values", () => {
    expect(toCamel({ status: "NEEDS_CORRECTION", field: "member.phone_number" })).toEqual({
      status: "NEEDS_CORRECTION",
      field: "member.phone_number",
    });
  });
});

describe("toSnake", () => {
  it("snakes camelCase keys deeply", () => {
    expect(toSnake({ applicationType: "FIRST_TIME", rows: [{ rowNumber: 1 }] })).toEqual({
      application_type: "FIRST_TIME",
      rows: [{ row_number: 1 }],
    });
  });
});
