import { useId } from "react";
import { Link } from "react-router";
import type { Application } from "@/api/types";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ar, t } from "@/i18n/ar";
import { formatDate, formatMoney, formatRelativeTime } from "@/utils/format";
import { snapshotTotal } from "./useApplications";

function primaryAction(application: Application): { to: string; label: string; primary: boolean } {
  switch (application.status) {
    case "DRAFT":
      return { to: `/application/${application.id}`, label: ar.dashboard.continue, primary: true };
    case "NEEDS_CORRECTION":
      return { to: `/application/${application.id}/form`, label: ar.dashboard.correct, primary: true };
    default:
      return { to: `/application/${application.id}/status`, label: ar.dashboard.view, primary: false };
  }
}

/** One row of "طلباتي" (PROMPT.md §43). */
export function ApplicationCard({
  application,
  statusLabel,
}: {
  application: Application;
  statusLabel: string;
}) {
  const titleId = useId();
  const isDraft = application.status === "DRAFT";
  const needsCorrection = application.status === "NEEDS_CORRECTION";
  const total = snapshotTotal(application);
  const action = primaryAction(application);

  return (
    <article
      aria-labelledby={titleId}
      className="rounded-xl border border-border bg-white p-4 transition-colors hover:border-border-hover sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <h3 id={titleId} className="text-lg font-extrabold text-charcoal">
          {application.referenceNumber ? (
            <bdi dir="ltr">{application.referenceNumber}</bdi>
          ) : (
            t(ar.dashboard.draftTitle, { year: application.fiscalYear })
          )}
        </h3>
        <StatusBadge status={application.status} label={statusLabel} />
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm text-slate">
        {isDraft ? (
          <span className="inline-flex items-center gap-1.5">
            <Icon name="clock" className="size-4 text-muted" />
            {t(ar.dashboard.lastSaved, { when: formatRelativeTime(application.updatedAt) })}
          </span>
        ) : (
          <span>{t(ar.dashboard.submittedOn, { date: formatDate(application.submittedAt) })}</span>
        )}
        {total !== null ? <span className="text-base font-extrabold text-teal-deep">{formatMoney(total)}</span> : null}
      </div>

      {needsCorrection ? (
        <div className="mt-4 rounded-lg border-s-4 border-status-correction-fg bg-status-correction-bg p-3">
          <p className="text-sm font-bold text-status-correction-fg">{ar.dashboard.reviewNotes}</p>
          <p className="mt-1 whitespace-pre-line text-charcoal" dir="auto">
            {application.reviewNotes}
          </p>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        {!isDraft ? (
          <details className="group text-sm text-slate">
            <summary className="flex cursor-pointer list-none items-center gap-1 font-semibold text-charcoal [&::-webkit-details-marker]:hidden">
              <Icon name="chevron" mirror className="size-4 transition-transform group-open:rotate-90 rtl:group-open:-rotate-90" />
              {ar.dashboard.details}
            </summary>
            <div className="mt-2 space-y-1 ps-5">
              <p>{t(ar.dashboard.beneficiariesCount, { count: application.beneficiaries.length })}</p>
              {!needsCorrection ? (
                <p dir="auto">{application.reviewNotes || ar.dashboard.noReviewNotes}</p>
              ) : null}
            </div>
          </details>
        ) : (
          <span />
        )}
        <Link to={action.to} className={buttonClasses(action.primary ? "primary" : "outline")}>
          {action.label}
        </Link>
      </div>
    </article>
  );
}
