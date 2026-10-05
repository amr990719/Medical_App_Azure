import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createApplication, fetchApplications } from "@/api/endpoints/applications";
import { queryKeys } from "@/api/keys";
import type { Application } from "@/api/types";

export function useApplications() {
  return useQuery({ queryKey: queryKeys.applications.list(), queryFn: () => fetchApplications() });
}

/** POST /applications/: the fiscal-year draft, or the already active application. */
export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => createApplication(),
    onSuccess: (application) => {
      queryClient.setQueryData(queryKeys.applications.detail(application.id), application);
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.list() });
    },
  });
}

/** One application per doctor per fiscal year unless it was rejected (DB constraint, §16.1). */
export function hasActiveApplication(applications: readonly Application[], fiscalYear: number): boolean {
  return applications.some((app) => app.fiscalYear === fiscalYear && app.status !== "REJECTED");
}

/** Total from the frozen fee snapshot of a submitted application (never computed here). */
export function snapshotTotal(application: Application): number | null {
  const snapshot: unknown = application.feeSnapshot;
  if (typeof snapshot === "object" && snapshot !== null && "total" in snapshot) {
    const { total } = snapshot;
    return typeof total === "number" ? total : null;
  }
  return null;
}
