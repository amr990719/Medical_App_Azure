import { Navigate, useParams } from "react-router";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { useApplication } from "@/features/applications/useApplication";
import { completedSteps, useValidation } from "@/features/applications/useValidation";
import { ar } from "@/i18n/ar";

/**
 * `/application/:id` opens the right step: the status page once submitted; otherwise the first
 * step the server's validation does not report complete (form → receipt → review).
 */
export function ApplicationRedirectPage() {
  const { id = "" } = useParams();
  const application = useApplication(id);
  const editable = application.data?.isEditable === true;
  const validation = useValidation(id, editable);
  const error = application.error ?? validation.error;

  if (error) {
    return (
      <FullPageStatus
        isError
        message={error.message}
        onRetry={() => {
          void application.refetch();
          void validation.refetch();
        }}
      />
    );
  }
  if (application.data && !editable) return <Navigate to={`/application/${id}/status`} replace />;
  if (!validation.data) return <FullPageStatus message={ar.common.loading} />;

  const done = completedSteps(validation.data.stepsComplete);
  const formDone = [1, 2, 3].every((step) => done.has(step));
  const target = !formDone ? "form" : done.has(4) ? "review" : "payment";
  return <Navigate to={`/application/${id}/${target}`} replace />;
}
