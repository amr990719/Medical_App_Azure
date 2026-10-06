import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { useAdminApplication } from "@/features/admin/queries";
import { toDraftPreset } from "@/features/admin/toDraftPreset";
import { ApplicationFormProvider } from "@/features/application-form/ApplicationFormProvider";
import { PaperForm } from "@/features/application-form/PaperForm";
import { ar } from "@/i18n/ar";
import { formatDate } from "@/utils/format";

/**
 * `/admin/applications/:id/print` — the same A4 sheet as the doctor's print view, fed from the
 * admin endpoint. National IDs are masked unless the admin reveals them (audited, as on the
 * detail page).
 */
export function AdminPrintPage() {
  const { id = "" } = useParams();
  const [revealed, setRevealed] = useState(false);
  const query = useAdminApplication(id, revealed);
  const app = query.data;
  const preset = useMemo(() => (app ? toDraftPreset(app) : undefined), [app]);

  if (query.error) {
    return <FullPageStatus isError message={query.error.message} onRetry={() => void query.refetch()} />;
  }
  if (!app || !preset) return <FullPageStatus message={ar.common.loading} />;

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
          <Link to={`/admin/applications/${id}`} className={buttonClasses("ghost")}>
            <Icon name="arrow" mirror className="size-4 rotate-180" />
            {ar.admin.print.back}
          </Link>
          <p className="min-w-0 flex-1 text-sm text-muted">{ar.print.hint}</p>
          <Button variant="ghost" onClick={() => setRevealed((value) => !value)} disabled={query.isFetching}>
            {revealed ? ar.admin.detail.hideFullId : ar.admin.detail.showFullId}
          </Button>
          <Button onClick={() => window.print()}>
            <Icon name="print" className="size-4" />
            {ar.print.print}
          </Button>
        </div>
      </div>
      <main id="main" tabIndex={-1} className="print-root mx-auto max-w-[210mm] px-2 py-4 outline-none sm:px-0 sm:py-8">
        {/* Keyed by the reveal state: the sheet is built once from its data source. */}
        <ApplicationFormProvider key={`${id}-${revealed && app.doctor.nationalId ? "full" : "masked"}`} applicationId={id} preset={preset}>
          <PaperForm mode="print" banner={banner} />
        </ApplicationFormProvider>
      </main>
    </div>
  );
}
