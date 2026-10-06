import { useId, useState } from "react";
import type { AdminApplicationDetail, ApplicationStatus, DocumentSummary, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { ar, t } from "@/i18n/ar";
import { formatMoney } from "@/utils/format";
import { ActionDialog } from "./ActionDialog";
import { choiceLabel } from "./labels";
import { PaymentBadge } from "./PaymentBadge";
import { usePaymentReview } from "./queries";

/** Statuses in which the server accepts a payment decision (D23). */
const PAYMENT_REVIEWABLE = new Set<ApplicationStatus>(["SUBMITTED", "UNDER_REVIEW", "NEEDS_CORRECTION"]);

type Decision = "CONFIRMED" | "REJECTED";

/** Receipt + confirm/reject (PROMPT.md §44). A note goes to the internal notes (D52). */
export function PaymentPanel({
  application,
  reference,
  onView,
  onDone,
}: {
  application: AdminApplicationDetail;
  reference: ReferenceData | undefined;
  onView: (document: DocumentSummary) => void;
  onDone: (message: string) => void;
}) {
  const titleId = useId();
  const review = usePaymentReview(application.id);
  const [decision, setDecision] = useState<Decision | null>(null);
  const receipt = application.documents.find((doc) => doc.documentType === "PAYMENT_RECEIPT" && !doc.beneficiaryId);
  const reviewable = Boolean(receipt) && PAYMENT_REVIEWABLE.has(application.status);
  const label = (status: string) => choiceLabel(reference?.paymentStatuses, status);
  const total = application.feeSnapshot?.total;

  const close = () => {
    setDecision(null);
    review.reset();
  };

  return (
    <section aria-labelledby={titleId} className="space-y-3 rounded-xl border border-border bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
          {ar.admin.payment.title}
        </h2>
        <PaymentBadge status={application.paymentStatus} label={label(application.paymentStatus)} />
      </div>

      {receipt ? (
        <Button variant="ghost" onClick={() => onView(receipt)} className="w-full justify-start border border-border">
          <Icon name="file" className="size-4" />
          {ar.admin.payment.viewReceipt}
        </Button>
      ) : (
        <p className="text-sm text-slate">{ar.admin.payment.noReceipt}</p>
      )}

      {reviewable ? (
        <div className="flex flex-wrap gap-2">
          {application.paymentStatus !== "CONFIRMED" ? (
            <Button onClick={() => setDecision("CONFIRMED")}>{ar.admin.payment.confirm}</Button>
          ) : null}
          {application.paymentStatus !== "REJECTED" ? (
            <Button variant="outline" onClick={() => setDecision("REJECTED")}>
              {ar.admin.payment.reject}
            </Button>
          ) : null}
        </div>
      ) : receipt ? (
        <p className="text-xs text-muted">{ar.admin.payment.locked}</p>
      ) : null}

      {decision ? (
        <ActionDialog
          title={decision === "CONFIRMED" ? ar.admin.payment.confirm : ar.admin.payment.rejectTitle}
          body={
            decision === "CONFIRMED"
              ? t(ar.admin.payment.confirmBody, { total: total === undefined ? "" : formatMoney(total) })
              : ar.admin.payment.rejectBody
          }
          notesLabel={ar.admin.payment.noteLabel}
          confirmVariant={decision === "REJECTED" ? "danger" : "primary"}
          busy={review.isPending}
          error={review.error?.message ?? null}
          onClose={close}
          onConfirm={(note) =>
            review.mutate(
              { paymentStatus: decision, note },
              {
                onSuccess: (detail) => {
                  close();
                  onDone(t(ar.admin.payment.done, { status: label(detail.paymentStatus) }));
                },
              },
            )
          }
        />
      ) : null}
    </section>
  );
}
