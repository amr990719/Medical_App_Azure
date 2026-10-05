import { useEffect, useRef } from "react";
import { Navigate } from "react-router";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { useCreateApplication } from "@/features/applications/useApplications";
import { ar } from "@/i18n/ar";

/**
 * /application/new: POST /applications/ creates the fiscal-year draft or returns the active one
 * (idempotent on the server), then opens it.
 */
export function NewApplicationPage() {
  const create = useCreateApplication();
  const started = useRef(false);
  const { mutate } = create;

  useEffect(() => {
    if (started.current) return; // StrictMode mounts effects twice in development
    started.current = true;
    mutate();
  }, [mutate]);

  if (create.data) return <Navigate to={`/application/${create.data.id}`} replace />;
  if (create.error) {
    return <FullPageStatus isError message={create.error.message} onRetry={() => create.mutate()} />;
  }
  return <FullPageStatus message={ar.pages.creatingApplication} />;
}
