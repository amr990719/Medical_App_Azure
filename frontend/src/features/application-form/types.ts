import type { components } from "@/api/schema";
import type { ApplicationType, Kinship } from "@/api/types";

type Schemas = components["schemas"];
export type SyndicateType = Schemas["SyndicateTypeEnum"];
export type WorkStatus = Schemas["WorkStatusEnum"];
export type Religion = Schemas["ReligionEnum"];
export type Gender = Schemas["GenderEnum"];

/** PROMPT.md §10.1 — the member part of the paper form (camelCase; the API is snake_case). */
export type MemberFields = {
  applicationType: ApplicationType;
  syndicateType: SyndicateType | "";
  subSyndicate: string;
  registrationNumber: string;
  treatmentCardNumber: string;
  syndicateRegistrationYear: string;
  workStatus: WorkStatus | "";
  memberName: string;
  religion: Religion | "";
  nationalId: string;
  gender: Gender | "";
  birthYear: string;
  governorate: string;
  neighborhood: string;
  address: string;
  mobile: string;
  email: string;
  declarationName: string;
};

export type MemberField = keyof MemberFields;

/**
 * One row of the 10-row table. Documents are NOT kept here: they come from the server
 * (application query) by `id`, so they are never raw `File`s waiting for the end (§10.1).
 */
export type BeneficiaryRow = {
  id?: string;
  kinship: Kinship | "";
  name: string;
  birthYear: string;
  nationalId: string;
};

export type BeneficiaryField = Exclude<keyof BeneficiaryRow, "id">;

export type ApplicationFormState = MemberFields & {
  /** Always `max_beneficiaries` rows in the UI. */
  beneficiaries: BeneficiaryRow[];
};

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export const emptyRow = (): BeneficiaryRow => ({ kinship: "", name: "", birthYear: "", nationalId: "" });
