import { apiFetch } from "../client";
import { toCamel } from "../case";
import type { ApiReferenceData, ReferenceData } from "../types";

export async function fetchReferenceData(): Promise<ReferenceData> {
  return toCamel(await apiFetch<ApiReferenceData>("/reference-data/"));
}
