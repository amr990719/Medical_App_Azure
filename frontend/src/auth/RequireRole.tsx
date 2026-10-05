import { Navigate, Outlet } from "react-router";
import type { Role } from "@/api/types";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { ar } from "@/i18n/ar";
import { homeFor, useSession } from "./useSession";

/**
 * Route guard: signed-out visitors go to the landing page, the other role goes to its own home.
 * UX only: the API enforces roles and ownership on every endpoint.
 */
export function RequireRole({ role }: { role: Role }) {
  const { user, isLoading, error, refetch } = useSession();

  if (isLoading) return <FullPageStatus message={ar.common.loading} />;
  if (error) {
    return <FullPageStatus message={error.message} onRetry={() => void refetch()} isError />;
  }
  if (!user) return <Navigate to="/" replace />;
  if (user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  return <Outlet />;
}
