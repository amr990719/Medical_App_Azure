/**
 * API ⇄ form state mapping (PROMPT.md §10). The member part of the paper form is stored in two
 * resources: the doctor profile (`PATCH /profile/`) and the application (`PATCH /applications/{id}/`).
 * Beneficiary rows map to `/applications/{id}/beneficiaries/`.
 */
import type { ApplicationPatch } from "@/api/endpoints/applications";
import type { BeneficiaryPayload } from "@/api/endpoints/beneficiaries";
import type { OcrFields } from "@/api/endpoints/documents";
import type { ProfilePatch } from "@/api/endpoints/profile";
import type { Application, Beneficiary, DoctorProfile, DocumentType, Kinship } from "@/api/types";
import { digitsOnly } from "@/utils/digits";
import {
  emptyRow,
  type ApplicationFormState,
  type BeneficiaryField,
  type BeneficiaryRow,
  type MemberField,
  type MemberFields,
} from "./types";

/** Member field → profile API field. */
const PROFILE_FIELDS = {
  memberName: "full_name",
  nationalId: "national_id",
  birthYear: "birth_year",
  gender: "gender",
  religion: "religion",
  mobile: "phone_number",
  syndicateType: "syndicate_type",
  subSyndicate: "sub_syndicate",
  registrationNumber: "syndicate_registration_number",
  syndicateRegistrationYear: "syndicate_registration_year",
  treatmentCardNumber: "treatment_card_number",
  governorate: "governorate",
  neighborhood: "neighborhood",
  address: "address",
} as const satisfies Partial<Record<MemberField, keyof ProfilePatch>>;

/** Member field → application API field. */
const APPLICATION_FIELDS = {
  applicationType: "application_type",
  workStatus: "work_status",
  declarationName: "declaration_name",
} as const satisfies Partial<Record<MemberField, keyof ApplicationPatch>>;

const ROW_FIELDS = {
  kinship: "kinship",
  name: "full_name",
  birthYear: "birth_year",
  nationalId: "national_id",
} as const satisfies Record<BeneficiaryField, keyof BeneficiaryPayload>;

type ProfileField = keyof typeof PROFILE_FIELDS;
type ApplicationField = keyof typeof APPLICATION_FIELDS;

export const isProfileField = (field: MemberField): field is ProfileField => field in PROFILE_FIELDS;
export const isApplicationField = (field: MemberField): field is ApplicationField => field in APPLICATION_FIELDS;

const YEAR_FIELDS = new Set<string>(["birthYear", "syndicateRegistrationYear"]);

/**
 * Value to send for a field, or `undefined` while it is still being typed (a 7-digit national
 * ID or a 3-digit year stays local until complete — drafts enforce formats, §10.3).
 */
function wireValue(field: string, value: string): string | number | null | undefined {
  if (field === "nationalId") {
    if (value === "") return null;
    return value.length === 14 ? value : undefined;
  }
  if (YEAR_FIELDS.has(field)) {
    if (value === "") return null;
    return /^\d{4}$/.test(value) ? Number(value) : undefined;
  }
  return value;
}

/** Fields whose current value cannot be sent yet. */
export const isSendable = (field: string, value: string) => wireValue(field, value) !== undefined;

export function profilePatch(state: MemberFields, fields: readonly MemberField[]): ProfilePatch {
  const patch: Record<string, unknown> = {};
  for (const field of fields) {
    if (!isProfileField(field)) continue;
    const value = wireValue(field, state[field]);
    if (value !== undefined) patch[PROFILE_FIELDS[field]] = value;
  }
  return patch as ProfilePatch;
}

export function applicationPatch(state: MemberFields, fields: readonly MemberField[]): ApplicationPatch {
  const patch: Record<string, unknown> = {};
  for (const field of fields) {
    if (isApplicationField(field)) patch[APPLICATION_FIELDS[field]] = state[field];
  }
  return patch as ApplicationPatch;
}

export function rowPatch(row: BeneficiaryRow, fields: readonly BeneficiaryField[]): BeneficiaryPayload {
  const patch: Record<string, unknown> = {};
  for (const field of fields) {
    const value = wireValue(field, row[field]);
    if (value !== undefined) patch[ROW_FIELDS[field]] = value;
  }
  return patch as BeneficiaryPayload;
}

const text = (value: string | number | null | undefined) => (value === null || value === undefined ? "" : String(value));

export function rowFromServer(beneficiary: Beneficiary): BeneficiaryRow {
  return {
    id: beneficiary.id,
    kinship: (beneficiary.kinship || "") as Kinship | "",
    name: beneficiary.fullName,
    birthYear: text(beneficiary.birthYear),
    nationalId: text(beneficiary.nationalId),
  };
}

export function toFormState(app: Application, profile: DoctorProfile, maxRows: number): ApplicationFormState {
  const beneficiaries = Array.from({ length: maxRows }, emptyRow);
  for (const beneficiary of app.beneficiaries) {
    const index = beneficiary.rowNumber - 1;
    if (index >= 0 && index < maxRows) beneficiaries[index] = rowFromServer(beneficiary);
  }
  return {
    applicationType: app.applicationType,
    syndicateType: profile.syndicateType ?? "",
    subSyndicate: profile.subSyndicate ?? "",
    registrationNumber: profile.syndicateRegistrationNumber ?? "",
    treatmentCardNumber: profile.treatmentCardNumber ?? "",
    syndicateRegistrationYear: text(profile.syndicateRegistrationYear),
    workStatus: app.workStatus,
    memberName: profile.fullName ?? "",
    religion: profile.religion ?? "",
    nationalId: text(profile.nationalId),
    gender: profile.gender ?? "",
    birthYear: text(profile.birthYear),
    governorate: profile.governorate ?? "",
    neighborhood: profile.neighborhood ?? "",
    address: profile.address ?? "",
    mobile: profile.phoneNumber ?? "",
    email: profile.email,
    declarationName: app.declarationName,
    beneficiaries,
  };
}

// ---- OCR suggestions (PROMPT.md §21.3) → form fields -----------------------------------------

const MEMBER_OCR_FIELDS: Record<string, MemberField> = {
  member_name: "memberName",
  national_id: "nationalId",
  birth_year: "birthYear",
  governorate: "governorate",
  neighborhood: "neighborhood",
  address: "address",
  gender: "gender",
  religion: "religion",
  registration_number: "registrationNumber",
  sub_syndicate: "subSyndicate",
  syndicate_registration_year: "syndicateRegistrationYear",
  syndicate_type: "syndicateType",
};

const ROW_OCR_FIELDS: Record<string, BeneficiaryField> = {
  name: "name",
  national_id: "nationalId",
  birth_year: "birthYear",
};

const normalizeOcr = (field: string, value: string | number) =>
  field === "nationalId" || YEAR_FIELDS.has(field) ? digitsOnly(String(value)) : String(value).trim();

/**
 * Port of the prototype's `handleOcrResult`: extracted values fill ONLY fields that are empty
 * right now; anything the doctor typed is kept.
 */
export function mergeMemberOcr<S extends MemberFields>(state: S, fields: OcrFields): { next: S; filled: MemberField[] } {
  const next = { ...state };
  const filled: MemberField[] = [];
  for (const [key, raw] of Object.entries(fields)) {
    const field = MEMBER_OCR_FIELDS[key];
    if (!field || field === "email") continue;
    const value = normalizeOcr(field, raw);
    if (!value || next[field] !== "") continue;
    (next as Record<MemberField, string>)[field] = value;
    filled.push(field);
  }
  return { next, filled };
}

/** Port of `updateBeneficiaryBatch` with the same empty-fields-only rule. */
export function mergeRowOcr(row: BeneficiaryRow, fields: OcrFields): { next: BeneficiaryRow; filled: BeneficiaryField[] } {
  const next = { ...row };
  const filled: BeneficiaryField[] = [];
  for (const [key, raw] of Object.entries(fields)) {
    const field = ROW_OCR_FIELDS[key];
    if (!field) continue;
    const value = normalizeOcr(field, raw);
    if (!value || next[field] !== "") continue;
    (next as Record<BeneficiaryField, string>)[field] = value;
    filled.push(field);
  }
  return { next, filled };
}

// ---- Server field paths → form locations (inline errors) -------------------------------------

export type FieldLocation =
  | { kind: "member"; field: MemberField }
  | { kind: "row"; index: number; field: BeneficiaryField }
  | { kind: "rowDocument"; index: number; documentType: DocumentType }
  | { kind: "memberDocument"; documentType: DocumentType }
  | { kind: "other" };

const API_TO_MEMBER: Record<string, MemberField> = Object.fromEntries([
  ...Object.entries(PROFILE_FIELDS).map(([form, api]) => [api, form]),
  ...Object.entries(APPLICATION_FIELDS).map(([form, api]) => [api, form]),
]);
const API_TO_ROW = Object.fromEntries(
  Object.entries(ROW_FIELDS).map(([form, api]) => [api, form]),
) as Record<string, BeneficiaryField>;

/** Map a validation path (`member.full_name`, `beneficiaries[3].birth_year`, …) to the form. */
export function fieldForPath(path: string): FieldLocation {
  const member = /^member\.(\w+)$/.exec(path);
  const memberField = member?.[1] ? API_TO_MEMBER[member[1]] : undefined;
  if (memberField) return { kind: "member", field: memberField };
  if (path === "declaration.name") return { kind: "member", field: "declarationName" };

  const rowDoc = /^beneficiaries\[(\d+)\]\.documents\.(\w+)$/.exec(path);
  if (rowDoc?.[1] && rowDoc[2]) {
    return { kind: "rowDocument", index: Number(rowDoc[1]) - 1, documentType: rowDoc[2] as DocumentType };
  }
  const row = /^beneficiaries\[(\d+)\]\.(\w+)$/.exec(path);
  const rowField = row?.[2] ? API_TO_ROW[row[2]] : undefined;
  if (row?.[1] && rowField) return { kind: "row", index: Number(row[1]) - 1, field: rowField };
  const doc = /^documents\.(\w+)$/.exec(path);
  if (doc?.[1]) return { kind: "memberDocument", documentType: doc[1] as DocumentType };
  return { kind: "other" };
}

/** Field errors of a refused profile/application PATCH (`{"national_id": [...]}`) → form fields. */
export function memberFieldErrors(fields: Record<string, string[]>): Partial<Record<MemberField, string>> {
  const errors: Partial<Record<MemberField, string>> = {};
  for (const [api, messages] of Object.entries(fields)) {
    const field = API_TO_MEMBER[api];
    if (field && messages[0]) errors[field] = messages[0];
  }
  return errors;
}

export function rowFieldErrors(fields: Record<string, string[]>): Partial<Record<BeneficiaryField, string>> {
  const errors: Partial<Record<BeneficiaryField, string>> = {};
  for (const [api, messages] of Object.entries(fields)) {
    const field = API_TO_ROW[api];
    if (field && messages[0]) errors[field] = messages[0];
  }
  return errors;
}
