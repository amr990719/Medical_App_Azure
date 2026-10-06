import { apiFetch } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type {
  ApiFeeQuote,
  ApiPage,
  ApiValidationResult,
  Application,
  ApplicationType,
  FeeQuote,
  Page,
  ValidationResult,
} from "../types";

type ApiApplication = components["schemas"]["Application"];

export async function fetchApplications(page = 1): Promise<Page<ApiApplication>> {
  return toCamel(await apiFetch<ApiPage<ApiApplication>>("/applications/", { query: { page } }));
}

export async function fetchApplication(id: string): Promise<Application> {
  return toCamel(await apiFetch<ApiApplication>(`/applications/${id}/`));
}

/** Creates the fiscal-year draft, or returns the active application (200). */
export async function createApplication(applicationType?: ApplicationType): Promise<Application> {
  const body = applicationType ? { application_type: applicationType } : {};
  return toCamel(await apiFetch<ApiApplication>("/applications/", { method: "POST", body }));
}

export async function fetchFeeQuote(id: string): Promise<FeeQuote> {
  return toCamel(await apiFetch<ApiFeeQuote>(`/applications/${id}/fees/`));
}

export async function fetchValidation(id: string): Promise<ValidationResult> {
  return toCamel(await apiFetch<ApiValidationResult>(`/applications/${id}/validation/`));
}

export type ApplicationPatch = components["schemas"]["PatchedApplicationUpdateRequest"];

export async function updateApplication(id: string, changes: ApplicationPatch): Promise<Application> {
  return toCamel(await apiFetch<ApiApplication>(`/applications/${id}/`, { method: "PATCH", body: changes }));
}

/** DRAFT → SUBMITTED or NEEDS_CORRECTION → SUBMITTED; a 400 carries every step error. */
export async function submitApplication(id: string): Promise<Application> {
  return toCamel(await apiFetch<ApiApplication>(`/applications/${id}/submit/`, { method: "POST" }));
}
