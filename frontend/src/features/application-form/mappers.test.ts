import { describe, expect, it } from "vitest";
import { toCamel } from "@/api/case";
import { apiApplication } from "@/test/fixtures";
import {
  fieldForPath,
  mergeMemberOcr,
  mergeRowOcr,
  profilePatch,
  rowPatch,
  toFormState,
} from "./mappers";
import { emptyRow, type ApplicationFormState } from "./types";

const profile = toCamel({
  id: "p1",
  email: "doctor@dev.local",
  full_name: "أحمد محمد علي حسن",
  national_id: null,
  date_of_birth: null,
  birth_year: null,
  gender: "",
  religion: "",
  phone_number: "",
  syndicate_type: "",
  sub_syndicate: "",
  syndicate_registration_number: "",
  syndicate_registration_year: null,
  treatment_card_number: "",
  governorate: "",
  neighborhood: "",
  address: "",
  updated_at: "2026-10-05T00:00:00Z",
} as const);

function stateWith(overrides: Partial<ApplicationFormState> = {}): ApplicationFormState {
  const base = toFormState(toCamel(apiApplication()), profile, 10);
  return { ...base, ...overrides };
}

describe("toFormState", () => {
  it("always has max_beneficiaries rows, placing server rows by row number", () => {
    const app = toCamel(
      apiApplication({
        beneficiaries: [
          {
            id: "b3",
            row_number: 3,
            kinship: "WIFE",
            full_name: "منى",
            birth_year: 1988,
            national_id: null,
            is_active: true,
            required_documents: [],
            documents: [],
            updated_at: "2026-10-05T00:00:00Z",
          },
        ],
      }),
    );
    const state = toFormState(app, profile, 10);
    expect(state.beneficiaries).toHaveLength(10);
    expect(state.beneficiaries[2]).toEqual({ id: "b3", kinship: "WIFE", name: "منى", birthYear: "1988", nationalId: "" });
    expect(state.beneficiaries[0]).toEqual(emptyRow());
    expect(state.memberName).toBe("أحمد محمد علي حسن");
    expect(state.email).toBe("doctor@dev.local");
  });
});

describe("OCR merge (PROMPT.md §10.2: never overwrite what the doctor typed)", () => {
  it("fills only empty member fields and maps API names to form fields", () => {
    const state = stateWith({ memberName: "اسم كتبه الطبيب", governorate: "" });
    const { next, filled } = mergeMemberOcr(state, {
      member_name: "أحمد محمد علي حسن",
      national_id: "28506150101234",
      birth_year: 1985,
      governorate: "القاهرة",
      unknown_field: "x",
    });
    expect(next.memberName).toBe("اسم كتبه الطبيب");
    expect(next.nationalId).toBe("28506150101234");
    expect(next.birthYear).toBe("1985");
    expect(next.governorate).toBe("القاهرة");
    expect(filled.sort()).toEqual(["birthYear", "governorate", "nationalId"]);
  });

  it("maps syndicate card and ID back fields", () => {
    const { next } = mergeMemberOcr(stateWith(), {
      registration_number: "12345",
      sub_syndicate: "القاهرة",
      syndicate_registration_year: 2014,
      syndicate_type: "HUMAN_MEDICINE",
      gender: "MALE",
      religion: "MUSLIM",
    });
    expect(next).toMatchObject({
      registrationNumber: "12345",
      subSyndicate: "القاهرة",
      syndicateRegistrationYear: "2014",
      syndicateType: "HUMAN_MEDICINE",
      gender: "MALE",
      religion: "MUSLIM",
    });
  });

  it("fills only empty beneficiary fields", () => {
    const row = { ...emptyRow(), kinship: "SON_MINOR" as const, birthYear: "2016" };
    const { next, filled } = mergeRowOcr(row, { name: "عمر أحمد محمد", birth_year: 2015, national_id: "" });
    expect(next).toEqual({ ...row, name: "عمر أحمد محمد", birthYear: "2016" });
    expect(filled).toEqual(["name"]);
  });
});

describe("payloads", () => {
  it("sends only complete national IDs and years, null when cleared", () => {
    const state = stateWith({ nationalId: "2850615", birthYear: "1985", syndicateRegistrationYear: "" });
    expect(profilePatch(state, ["nationalId", "birthYear", "syndicateRegistrationYear", "mobile"])).toEqual({
      birth_year: 1985,
      syndicate_registration_year: null,
      phone_number: "",
    });
    expect(profilePatch({ ...state, nationalId: "" }, ["nationalId"])).toEqual({ national_id: null });
  });

  it("builds beneficiary payloads", () => {
    const row = { kinship: "WIFE" as const, name: "منى", birthYear: "198", nationalId: "" };
    expect(rowPatch(row, ["kinship", "name", "birthYear", "nationalId"])).toEqual({
      kinship: "WIFE",
      full_name: "منى",
      national_id: null,
    });
  });
});

describe("fieldForPath", () => {
  it("maps server validation paths to form locations", () => {
    expect(fieldForPath("member.full_name")).toEqual({ kind: "member", field: "memberName" });
    expect(fieldForPath("member.work_status")).toEqual({ kind: "member", field: "workStatus" });
    expect(fieldForPath("beneficiaries[3].birth_year")).toEqual({ kind: "row", index: 2, field: "birthYear" });
    expect(fieldForPath("beneficiaries[2].documents.BIRTH_CERTIFICATE")).toEqual({
      kind: "rowDocument",
      index: 1,
      documentType: "BIRTH_CERTIFICATE",
    });
    expect(fieldForPath("documents.NATIONAL_ID_FRONT")).toEqual({
      kind: "memberDocument",
      documentType: "NATIONAL_ID_FRONT",
    });
    expect(fieldForPath("declaration.name")).toEqual({ kind: "member", field: "declarationName" });
    expect(fieldForPath("receipt")).toEqual({ kind: "other" });
  });
});
