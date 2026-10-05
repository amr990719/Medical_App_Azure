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
