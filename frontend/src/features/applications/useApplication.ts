import { useQuery } from "@tanstack/react-query";
import { fetchApplication } from "@/api/endpoints/applications";
import { queryKeys } from "@/api/keys";
import type { Application, ApplicationStatus } from "@/api/types";

/** Statuses that still change without the doctor doing anything (the admin is reviewing). */
const AWAITING_REVIEW = new Set<ApplicationStatus>(["SUBMITTED", "UNDER_REVIEW"]);

export function useApplication(id: string, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.applications.detail(id),
    queryFn: () => fetchApplication(id),
    // Status page: poll every 45 s (§43: 30–60 s) while waiting for the review; stop afterwards.
    refetchInterval: poll
      ? (query) => (query.state.data && AWAITING_REVIEW.has(query.state.data.status) ? 45_000 : false)
      : false,
  });
}

export const isAwaitingReview = (app: Application) => AWAITING_REVIEW.has(app.status);
