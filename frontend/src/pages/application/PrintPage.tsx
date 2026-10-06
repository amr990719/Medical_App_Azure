import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { ApplicationFormProvider } from "@/features/application-form/ApplicationFormProvider";
import { PaperForm } from "@/features/application-form/PaperForm";
import { useApplication } from "@/features/applications/useApplication";
import { ar } from "@/i18n/ar";
import { formatDate } from "@/utils/format";

/**
 * `/application/:id/print` — the A4 paper form (PROMPT.md §9.8): no app chrome, no stepper,
 * attachments panel, paperclips or modals; the reference number and submission date when they
 * exist. Rules for paper live in `src/print.css`.
 */
export function PrintPage() {
  const { id = "" } = useParams();
  const application = useApplication(id);

  if (application.error) {
    return <FullPageStatus isError message={application.error.message} onRetry={() => void application.refetch()} />;
  }
  const app = application.data;
  if (!app) return <FullPageStatus message={ar.common.loading} />;

  const backTo = app.isEditable ? `/application/${id}/form` : `/application/${id}/status`;
  const banner = app.referenceNumber ? (
    <p className="flex flex-wrap justify-between gap-x-6 gap-y-1 border-[1.5px] border-paper-line px-3 py-1.5 text-sm font-bold text-charcoal">
      <span>
        {ar.print.reference} <bdi dir="ltr">{app.referenceNumber}</bdi>
      </span>
      {app.submittedAt ? (
        <span>
          {ar.print.submittedAt} <span>{formatDate(app.submittedAt)}</span>
        </span>
      ) : null}
    </p>
  ) : null;

  return (
    <div className="min-h-dvh bg-smoke print:min-h-0 print:bg-paper">
      <div className="sticky top-0 z-40 border-b border-border bg-white/95 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-[210mm] flex-wrap items-center gap-3 px-3 py-2.5">
          <Link to={backTo} className={buttonClasses("ghost")}>
            <Icon name="arrow" mirror className="size-4 rotate-180" />
            {ar.print.back}
          </Link>
          <p className="min-w-0 flex-1 text-sm text-muted">{ar.print.hint}</p>
          <Button onClick={() => window.print()}>
            <Icon name="print" className="size-4" />
            {ar.print.print}
          </Button>
        </div>
      </div>
      <main id="main" tabIndex={-1} className="print-root mx-auto max-w-[210mm] px-2 py-4 outline-none sm:px-0 sm:py-8">
        <ApplicationFormProvider key={id} applicationId={id} readOnly>
          <PaperForm mode="print" banner={banner} />
        </ApplicationFormProvider>
      </main>
    </div>
  );
}
