import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "@/api/endpoints/auth";
import { queryKeys } from "@/api/keys";
import type { CurrentUser, Role } from "@/api/types";

/** The signed-in user from GET /auth/me/ (`null` when signed out). Also sets the CSRF cookie. */
export function useSession() {
  const query = useQuery({ queryKey: queryKeys.me, queryFn: fetchMe, staleTime: 5 * 60_000 });
  return {
    user: query.data?.user ?? null,
    isLoading: query.isPending,
    error: query.error,
    refetch: query.refetch,
  };
}

export function homeFor(role: Role): string {
  return role === "ADMIN" ? "/admin/dashboard" : "/dashboard";
}

/** First word of the display name, for the dashboard greeting. */
export function firstName(user: Pick<CurrentUser, "displayName"> | null): string {
  return user?.displayName.trim().split(/\s+/)[0] ?? "";
}
