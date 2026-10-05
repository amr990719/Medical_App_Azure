import { type QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { SESSION_EXPIRED_EVENT } from "@/api/client";
import { queryKeys } from "@/api/keys";

/** A 401 anywhere re-checks /auth/me/; the route guards then send the visitor to "/". */
function SessionExpiryListener() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const onExpired = () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [queryClient]);
  return null;
}

export function AppProviders({
  queryClient,
  children,
}: {
  queryClient: QueryClient;
  children: ReactNode;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionExpiryListener />
      {children}
    </QueryClientProvider>
  );
}
