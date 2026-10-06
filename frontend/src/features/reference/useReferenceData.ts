import { useQuery } from "@tanstack/react-query";
import { fetchReferenceData } from "@/api/endpoints/reference";
import { queryKeys } from "@/api/keys";
import type { ApplicationStatus, ReferenceData } from "@/api/types";

/** Enums, labels, rules and limits from the server; cached for the whole session. */
export function useReferenceData() {
  return useQuery({
    queryKey: queryKeys.referenceData,
    queryFn: fetchReferenceData,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function statusLabel(reference: ReferenceData | undefined, status: ApplicationStatus): string {
  return reference?.statuses.find((choice) => choice.value === status)?.label ?? status;
}
