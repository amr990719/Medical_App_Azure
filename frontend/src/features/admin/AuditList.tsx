import { useId, useState } from "react";
import type { AuditEntry, DocumentType, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ar } from "@/i18n/ar";
import { formatDate } from "@/utils/format";
import { choiceLabel, documentTypeLabel } from "./labels";
import { useAudit } from "./queries";

const timeFormat = new Intl.DateTimeFormat("ar-EG", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Cairo" });

/** A short, value-free description of what changed (metadata never holds personal data, §39). */
function detail(entry: AuditEntry, reference: ReferenceData | undefined): string {
  const { from, to, documentType } = entry.metadata as { from?: string; to?: string; documentType?: DocumentType };
  if (entry.action === "APPLICATION_STATUS_CHANGED" && from && to) {
    return `${choiceLabel(reference?.statuses, from)} ← ${choiceLabel(reference?.statuses, to)}`;
  }
  if (entry.action === "PAYMENT_STATUS_CHANGED" && from && to) {
    return `${choiceLabel(reference?.paymentStatuses, from)} ← ${choiceLabel(reference?.paymentStatuses, to)}`;
  }
  if (documentType) return documentTypeLabel(reference, documentType);
  return "";
}

function AuditPage({ applicationId, page, reference }: { applicationId: string; page: number; reference: ReferenceData | undefined }) {
  const audit = useAudit(applicationId, page);
  if (audit.isLoading) return <Skeleton className="h-10 w-full" />;
  if (audit.error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {audit.error.message}
      </p>
    );
  }
  return (
    <>
      {audit.data?.results.map((entry) => {
        const what = detail(entry, reference);
        return (
          <li key={entry.id} className="relative border-s-2 border-border ps-4 pb-3 last:pb-0">
            <span className="absolute -start-[5px] top-1.5 size-2 rounded-full bg-teal" aria-hidden />
            <p className="text-sm font-bold text-charcoal">
              {ar.admin.audit.actions[entry.action] ?? entry.action}
              {what ? <span className="ms-2 font-normal text-slate">{what}</span> : null}
            </p>
            <p className="text-xs text-muted">
              <bdi dir="ltr">{entry.userEmail ?? ar.admin.audit.system}</bdi> · {formatDate(entry.timestamp)}{" "}
              {timeFormat.format(new Date(entry.timestamp))}
            </p>
          </li>
        );
      })}
    </>
  );
}

/** Audit history of the application and its documents, newest first, 25 per page. */
export function AuditList({ applicationId, reference }: { applicationId: string; reference: ReferenceData | undefined }) {
  const titleId = useId();
  const [pages, setPages] = useState(1);
  const last = useAudit(applicationId, pages);
  const hasMore = Boolean(last.data?.next);

  return (
    <section aria-labelledby={titleId} className="space-y-3 rounded-xl border border-border bg-white p-5">
      <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
        {ar.admin.audit.title}
      </h2>
      {last.data?.count === 0 ? (
        <p className="text-sm text-slate">{ar.admin.audit.empty}</p>
      ) : (
        <ol className="space-y-0">
          {Array.from({ length: pages }, (_, index) => (
            <AuditPage key={index} applicationId={applicationId} page={index + 1} reference={reference} />
          ))}
        </ol>
      )}
      {hasMore ? (
        <Button variant="ghost" onClick={() => setPages((n) => n + 1)}>
          {ar.admin.audit.more}
        </Button>
      ) : null}
    </section>
  );
}
