import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { logout } from "@/api/endpoints/auth";
import { queryKeys } from "@/api/keys";
import { browser } from "@/utils/browser";

/**
 * POST /auth/logout/, then drop every cached query (form state included, PROMPT.md §10.2) and
 * either continue to the Entra logout page or show /signed-out.
 */
export function useSignOut() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return useMutation({
    mutationFn: async () => {
      try {
        return await logout();
      } catch {
        // An already-expired session still ends on the signed-out page.
        return { entraLogoutUrl: null };
      }
    },
    onSuccess: ({ entraLogoutUrl }) => {
      queryClient.clear();
      queryClient.setQueryData(queryKeys.me, null);
      if (entraLogoutUrl) {
        browser.assign(entraLogoutUrl);
      } else {
        navigate("/signed-out", { replace: true });
      }
    },
  });
}
