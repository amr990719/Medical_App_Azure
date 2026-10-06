import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchValidation } from "@/api/endpoints/applications";
import { queryKeys } from "@/api/keys";

/** GET /validation/: every error grouped by step + step completion (server-authoritative). */
export function useValidation(applicationId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.applications.validation(applicationId),
    queryFn: () => fetchValidation(applicationId),
    enabled,
  });
}

/** A fresh validation result, never a cached one (gates navigation and submission). */
export function useFreshValidation(applicationId: string) {
  const queryClient = useQueryClient();
  return () =>
    queryClient.fetchQuery({
      queryKey: queryKeys.applications.validation(applicationId),
      queryFn: () => fetchValidation(applicationId),
      staleTime: 0,
    });
}

/** Steps the server reports complete, for the ProgressStepper. */
export function completedSteps(stepsComplete: Record<string, boolean> | undefined): Set<number> {
  return new Set(
    Object.entries(stepsComplete ?? {})
      .filter(([, done]) => done)
      .map(([step]) => Number(step)),
  );
}
