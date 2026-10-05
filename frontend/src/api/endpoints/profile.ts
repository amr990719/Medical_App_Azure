import { apiFetch } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type { DoctorProfile } from "../types";

export async function fetchProfile(): Promise<DoctorProfile> {
  return toCamel(await apiFetch<components["schemas"]["DoctorProfile"]>("/profile/"));
}
