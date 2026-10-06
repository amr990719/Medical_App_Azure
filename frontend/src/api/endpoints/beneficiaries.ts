import { apiFetch } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type { Beneficiary } from "../types";

type ApiBeneficiary = components["schemas"]["Beneficiary"];
export type BeneficiaryPayload = components["schemas"]["PatchedBeneficiaryWriteRequest"];

const base = (applicationId: string) => `/applications/${applicationId}/beneficiaries/`;

export async function createBeneficiary(applicationId: string, body: BeneficiaryPayload): Promise<Beneficiary> {
  return toCamel(await apiFetch<ApiBeneficiary>(base(applicationId), { method: "POST", body }));
}

export async function updateBeneficiary(
  applicationId: string,
  id: string,
  body: BeneficiaryPayload,
): Promise<Beneficiary> {
  return toCamel(await apiFetch<ApiBeneficiary>(`${base(applicationId)}${id}/`, { method: "PATCH", body }));
}

/** Deletes the row and its documents (server side). */
export async function deleteBeneficiary(applicationId: string, id: string): Promise<void> {
  await apiFetch<undefined>(`${base(applicationId)}${id}/`, { method: "DELETE" });
}
