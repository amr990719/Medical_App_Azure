import { useQuery } from "@tanstack/react-query";
import { fetchFeeQuote } from "@/api/endpoints/applications";
import { queryKeys } from "@/api/keys";

/** Live server quote while editable, the frozen snapshot afterwards. Refetched after autosave. */
export function useFeeQuote(applicationId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.applications.fees(applicationId ?? ""),
    queryFn: () => fetchFeeQuote(applicationId ?? ""),
    enabled: Boolean(applicationId),
  });
}
