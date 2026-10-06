/**
 * API fixtures captured from the real backend (development settings, seed_dev_data) so the
 * tests exercise the same snake_case payloads the SPA receives.
 */
import { http, HttpResponse } from "msw";
import type { components } from "@/api/schema";
import type { ApiFeeQuote, ApiPage, ApiReferenceData } from "@/api/types";
import draft from "./fixtures/application-draft.json";
import referenceData from "./fixtures/reference-data.json";

type Schemas = components["schemas"];
export type ApiApplication = Schemas["Application"];
export type ApiMe = Schemas["Me"];

export const API = "http://localhost:3000/api/v1";

export const apiReferenceData = referenceData as ApiReferenceData;

export const meDoctor: ApiMe = {
  user: {
    id: "19a6266e-89ff-40c4-a046-5741d3d75de1",
    email: "doctor@dev.local",
    role: "DOCTOR",
    display_name: "أحمد محمد علي حسن",
    has_profile: true,
  },
  csrf_token: "csrf-doctor",
};

export const meAdmin: ApiMe = {
  user: {
    id: "d876d404-7fb2-425f-890a-381f1346853c",
    email: "admin@dev.local",
    role: "ADMIN",
    display_name: "مسؤول المراجعة (تجريبي)",
    has_profile: false,
  },
  csrf_token: "csrf-admin",
};

export function apiApplication(overrides: Partial<ApiApplication> = {}): ApiApplication {
  return { ...(draft as unknown as ApiApplication), ...overrides };
}

export const submittedApplication = apiApplication({
  id: "5f0c1a52-0000-4000-8000-000000000123",
  status: "UNDER_REVIEW",
  payment_status: "PENDING_REVIEW",
  reference_number: "MED-2026-000123",
  submitted_at: "2026-10-03T09:15:00+03:00",
  is_editable: false,
  fee_snapshot: { total: 3025, tier: 3 },
});

export function page<T>(results: T[]): ApiPage<T> {
  return { count: results.length, next: null, previous: null, results };
}

export const feeQuote: ApiFeeQuote = {
  fiscal_year: 2026,
  tier: 3,
  breakdown: [
    { label: "العضو الأصلي", fee: 750, note: "" },
    { label: "زوجة", fee: 750, note: "" },
    { label: "ابن (18 سنة أو أقل)", fee: 750, note: "" },
    { label: "رسوم إدارية", fee: 775, note: "" },
  ],
  admin_fee: 775,
  total: 3025,
  is_valid: true,
  error_message: "",
  schedule_id: "5ed606f5-aa47-4703-8b6c-83ab2469c007",
};

const unauthenticated = () =>
  HttpResponse.json(
    { error: { code: "NOT_AUTHENTICATED", message: "يرجى تسجيل الدخول", fields: {} } },
    { status: 401 },
  );

export const handlers = {
  me: (me: ApiMe | null) =>
    http.get(`${API}/auth/me/`, () => (me ? HttpResponse.json(me) : unauthenticated())),
  referenceData: () => http.get(`${API}/reference-data/`, () => HttpResponse.json(apiReferenceData)),
  applications: (apps: ApiApplication[]) =>
    http.get(`${API}/applications/`, () => HttpResponse.json(page(apps))),
  devUsersDisabled: () =>
    http.get(`${API}/auth/dev/users/`, () =>
      HttpResponse.json({ error: { code: "NOT_FOUND", message: "غير موجود", fields: {} } }, { status: 404 }),
    ),
};

// ---- Session 5: doctor flow fixtures --------------------------------------------------------

export type ApiProfile = Schemas["DoctorProfile"];
export type ApiBeneficiary = Schemas["Beneficiary"];
export type ApiDocument = Schemas["DocumentSummary"];

export const APP_ID = draft.id;

export function apiProfile(overrides: Partial<ApiProfile> = {}): ApiProfile {
  return {
    id: "8b1f4a52-0000-4000-8000-000000000001",
    email: "doctor@dev.local",
    full_name: "",
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
    updated_at: "2026-10-05T22:40:31+03:00",
    ...overrides,
  };
}

export function apiDocument(overrides: Partial<ApiDocument> = {}): ApiDocument {
  const id = overrides.id ?? "d-front";
  return {
    id,
    document_type: "NATIONAL_ID_FRONT",
    beneficiary_id: null,
    original_filename: "front.png",
    content_type: "image/png",
    file_size: 2048,
    scan_status: "SKIPPED",
    created_at: "2026-10-05T10:00:00+03:00",
    content_url: `/api/v1/documents/${id}/content/`,
    ...overrides,
  };
}

const requirement = (type: string, label: string, required: boolean, ocr: boolean) => ({
  type,
  label,
  required,
  ocr_capable: ocr,
});

export const SPOUSE_REQUIREMENTS = [
  requirement("BENEFICIARY_NATIONAL_ID", "بطاقة الرقم القومي", true, true),
  requirement("MARRIAGE_CERTIFICATE", "شهادة الزواج", true, false),
  requirement("INSURANCE_PRINT", "برينت تأميني", true, false),
];

export const CHILD_REQUIREMENTS = [
  requirement("BIRTH_CERTIFICATE", "شهادة الميلاد", true, true),
  requirement("BENEFICIARY_NATIONAL_ID", "بطاقة الرقم القومي", false, true),
];

export function apiBeneficiary(overrides: Partial<ApiBeneficiary> = {}): ApiBeneficiary {
  return {
    id: "b-wife",
    row_number: 1,
    kinship: "WIFE",
    full_name: "منى سعيد عبد الله",
    birth_year: 1988,
    national_id: null,
    is_active: true,
    required_documents: SPOUSE_REQUIREMENTS,
    documents: [],
    updated_at: "2026-10-05T22:40:31+03:00",
    ...overrides,
  };
}

export const cleanValidation = {
  is_valid: true,
  errors: [],
  by_step: { "1": [], "2": [], "3": [], "4": [], "5": [] },
  steps_complete: { "1": true, "2": true, "3": true, "4": false, "5": false },
  warnings: [],
  submit_ready: false,
};

export const draftHandlers = {
  profile: (profile: ApiProfile = apiProfile()) => http.get(`${API}/profile/`, () => HttpResponse.json(profile)),
  application: (app: ApiApplication) =>
    http.get(`${API}/applications/${app.id}/`, () => HttpResponse.json(app)),
  fees: (id: string = APP_ID, quote: ApiFeeQuote = feeQuote) =>
    http.get(`${API}/applications/${id}/fees/`, () => HttpResponse.json(quote)),
  validation: (id: string = APP_ID, result: object = cleanValidation) =>
    http.get(`${API}/applications/${id}/validation/`, () => HttpResponse.json(result)),
};
