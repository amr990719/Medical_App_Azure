import { Link, useLocation, useParams } from "react-router";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { isAwaitingReview, useApplication } from "@/features/applications/useApplication";
import { snapshotTotal } from "@/features/applications/useApplications";
import { StatusTimeline } from "@/features/applications/StatusTimeline";
import { statusLabel, useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { formatDate, formatMoney, formatRelativeTime } from "@/utils/format";

const S = ar.status;

/** `/application/:id/status` — confirmation, reference number, timeline, notes (PROMPT.md §43). */
export function StatusPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const justSubmitted = (location.state as { justSubmitted?: boolean } | null)?.justSubmitted === true;
  const application = useApplication(id, { poll: true });
  const reference = useReferenceData();

  if (application.error) {
    return <FullPageStatus isError message={application.error.message} onRetry={() => void application.refetch()} />;
  }
  const app = application.data;
  if (!app) return <FullPageStatus message={ar.common.loading} />;

  const total = snapshotTotal(app);
  const needsCorrection = app.status === "NEEDS_CORRECTION";

  return (
    <div className="mx-auto max-w-3xl space-y-5 px-4 py-6 sm:px-6">
      <h1 className="text-2xl font-extrabold text-charcoal">{S.title}</h1>

      {app.status === "DRAFT" ? (
        <div className="rounded-xl border border-border bg-white p-5">
          <p className="text-slate">{S.notSubmitted}</p>
          <Link to={`/application/${id}`} className={buttonClasses("primary", "md") + " mt-3"}>
            {S.continueDraft}
          </Link>
        </div>
      ) : (
        <>
          {justSubmitted ? (
            <div role="status" className="flex items-start gap-3 rounded-xl border border-teal/30 bg-teal-light p-4">
              <Icon name="check" className="mt-1 size-6 text-teal-deep" />
              <div>
                <p className="text-lg font-extrabold text-teal-deep">{S.submittedNow}</p>
                <p className="text-charcoal">{S.keepReference}</p>
              </div>
            </div>
          ) : null}

          <section className="rounded-2xl border border-border bg-white p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm font-bold text-slate">{S.reference}</p>
                <p className="mt-0.5 text-3xl font-extrabold text-charcoal sm:text-4xl">
                  <bdi dir="ltr">{app.referenceNumber}</bdi>
                </p>
              </div>
              <StatusBadge status={app.status} label={statusLabel(reference.data, app.status)} />
            </div>
            <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm text-slate sm:grid-cols-2">
              <div>
                <dt className="inline">{ar.print.submittedAt} </dt>
                <dd className="inline font-semibold text-charcoal">{formatDate(app.submittedAt)}</dd>
              </div>
              {total !== null ? (
                <div>
                  <dt className="inline">{S.total}: </dt>
                  <dd className="inline font-extrabold text-teal-deep">{formatMoney(total)}</dd>
                </div>
              ) : null}
            </dl>
            <div className="mt-6 border-t border-border pt-5">
              <StatusTimeline status={app.status} />
            </div>
            {isAwaitingReview(app) ? (
              <p className="mt-4 text-xs text-muted">
                {S.autoRefresh}{" "}
                {application.dataUpdatedAt
                  ? t(S.lastChecked, { when: formatRelativeTime(new Date(application.dataUpdatedAt).toISOString()) })
                  : null}
              </p>
            ) : null}
          </section>

          {app.reviewNotes ? (
            <section
              className={
                needsCorrection
                  ? "rounded-xl border-s-4 border-status-correction-fg bg-status-correction-bg p-4"
                  : "rounded-xl border border-border bg-white p-4"
              }
            >
              <h2 className="font-extrabold text-charcoal">{S.notes}</h2>
              <p className="mt-1 whitespace-pre-line text-charcoal" dir="auto">
                {app.reviewNotes}
              </p>
            </section>
          ) : null}

          <div className="flex flex-wrap gap-3">
            {needsCorrection ? (
              <Link to={`/application/${id}/form`} className={buttonClasses("primary", "lg")}>
                {S.correct}
              </Link>
            ) : null}
            <Link to={`/application/${id}/print`} className={buttonClasses("outline", "lg")}>
              <Icon name="print" className="size-4" />
              {S.print}
            </Link>
            <Link to="/dashboard" className={buttonClasses("ghost", "lg")}>
              {S.backToDashboard}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
