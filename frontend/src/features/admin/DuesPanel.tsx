import { useId, useState } from "react";
import type { AdminDuesReceipt, AdminDuesRequest, DocumentSummary, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { DuesStatusBadge } from "@/features/dues/DuesStatusBadge";
import { ar, t } from "@/i18n/ar";
import { formatAmount, formatDate } from "@/utils/format";
import { ActionDialog } from "./ActionDialog";
import { choiceLabel } from "./labels";
import { useCancelDuesRequest, useReviewDuesReceipt } from "./queries";

const D = ar.admin.dues;

type Pending = { kind: "confirm" | "reject" | "cancel"; dues: AdminDuesRequest; receipt?: AdminDuesReceipt };

function ReceiptItem({
  receipt,
  index,
  reference,
  onView,
}: {
  receipt: AdminDuesReceipt;
  index: number;
  reference: ReferenceData | undefined;
  onView: (document: DocumentSummary, label: string) => void;
}) {
  const label = t(D.receiptLabel, { n: index });
  return (
    <li className="space-y-1 rounded-lg border border-border bg-smoke p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-charcoal">
          {t(D.receiptUploaded, { n: index, date: formatDate(receipt.createdAt) })}
        </span>
        <DuesStatusBadge status={receipt.status} label={choiceLabel(reference?.duesReceiptStatuses, receipt.status)} />
        <Button
          variant="ghost"
          onClick={() => onView(receipt.document, label)}
          className="ms-auto border border-border bg-white"
        >
          <Icon name="file" className="size-4" />
          {t(D.viewReceipt, { n: index })}
        </Button>
      </div>
      {receipt.rejectionReason ? (
        <p className="whitespace-pre-line text-status-rejected-fg">{t(D.rejectionReason, { reason: receipt.rejectionReason })}</p>
      ) : null}
      {receipt.reviewedAt ? (
        <p className="text-xs text-muted">
          {t(D.reviewedBy, { who: receipt.reviewedByEmail ?? "", date: formatDate(receipt.reviewedAt) })}
        </p>
      ) : null}
    </li>
  );
}

function DuesCard({
  dues,
  reference,
  onView,
  onAction,
  busy,
}: {
  dues: AdminDuesRequest;
  reference: ReferenceData | undefined;
  onView: (document: DocumentSummary, label: string) => void;
  onAction: (pending: Pending) => void;
  busy: boolean;
}) {
  const titleId = useId();
  const pendingReceipt = dues.receipts.find((receipt) => receipt.status === "PENDING_REVIEW");
  const can = (action: AdminDuesRequest["allowedActions"][number]) => dues.allowedActions.includes(action);
  return (
    <article aria-labelledby={titleId} className="space-y-3 rounded-xl border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p id={titleId} className="text-xl font-extrabold text-charcoal">
          <bdi>{formatAmount(dues.amount)}</bdi>
        </p>
        <DuesStatusBadge status={dues.status} label={choiceLabel(reference?.duesRequestStatuses, dues.status)} />
      </div>
      <p className="whitespace-pre-line text-charcoal" dir="auto">
        {dues.reason}
      </p>
      <p className="text-xs text-muted">
        {t(D.requestedBy, { who: dues.createdByEmail, date: formatDate(dues.createdAt) })}
        {dues.resolvedAt ? ` · ${t(D.resolvedBy, { who: dues.resolvedByEmail ?? "", date: formatDate(dues.resolvedAt) })}` : null}
      </p>
      {dues.cancellationReason ? (
        <p className="text-sm text-slate">{t(D.cancellationReason, { reason: dues.cancellationReason })}</p>
      ) : null}

      <h3 className="text-sm font-extrabold text-charcoal">{D.receipts}</h3>
      {dues.receipts.length === 0 ? (
        <p className="text-sm text-slate">{D.noReceipts}</p>
      ) : (
        <ol className="space-y-2">
          {dues.receipts.map((receipt, index) => (
            <ReceiptItem key={receipt.id} receipt={receipt} index={index + 1} reference={reference} onView={onView} />
          ))}
        </ol>
      )}

      {dues.allowedActions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {can("CONFIRM_RECEIPT") && pendingReceipt ? (
            <Button onClick={() => onAction({ kind: "confirm", dues, receipt: pendingReceipt })} disabled={busy}>
              {D.confirm}
            </Button>
          ) : null}
          {can("REJECT_RECEIPT") && pendingReceipt ? (
            <Button variant="outline" onClick={() => onAction({ kind: "reject", dues, receipt: pendingReceipt })} disabled={busy}>
              {D.reject}
            </Button>
          ) : null}
          {can("CANCEL") ? (
            <Button variant="ghost" className="border border-border" onClick={() => onAction({ kind: "cancel", dues })} disabled={busy}>
              {D.cancel}
            </Button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

/**
 * «المستحقات النقابية»: additional dues requested from the member, apart from the treatment fee
 * and its receipt. Every receipt stays listed with its review; the buttons are the server's
 * `allowed_actions` for each request.
 */
export function DuesPanel({
  applicationId,
  requests,
  reference,
  onView,
  onDone,
}: {
  applicationId: string;
  requests: AdminDuesRequest[];
  reference: ReferenceData | undefined;
  onView: (document: DocumentSummary, label: string) => void;
  onDone: (message: string) => void;
}) {
  const titleId = useId();
  const review = useReviewDuesReceipt(applicationId);
  const cancel = useCancelDuesRequest(applicationId);
  const [pending, setPending] = useState<Pending | null>(null);
  const busy = review.isPending || cancel.isPending;

  const close = () => {
    setPending(null);
    review.reset();
    cancel.reset();
  };
  const finish = (message: string) => () => {
    close();
    onDone(message);
  };
  const run = (text: string) => {
    if (!pending) return;
    const { dues, receipt } = pending;
    if (pending.kind === "cancel") {
      cancel.mutate({ duesId: dues.id, reason: text }, { onSuccess: finish(D.cancelled) });
    } else if (receipt) {
      const decision = pending.kind === "confirm" ? "CONFIRMED" : "REJECTED";
      review.mutate(
        { duesId: dues.id, receiptId: receipt.id, decision, reason: text },
        { onSuccess: finish(decision === "CONFIRMED" ? D.confirmed : D.rejected) },
      );
    }
  };

  return (
    <section aria-labelledby={titleId} className="space-y-3 rounded-xl border border-border bg-white p-5">
      <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
        {D.title}
      </h2>
      <p className="text-sm text-slate">{D.intro}</p>
      {requests.length === 0 ? (
        <p className="text-sm text-slate">{D.empty}</p>
      ) : (
        requests.map((dues) => (
          <DuesCard key={dues.id} dues={dues} reference={reference} onView={onView} onAction={setPending} busy={busy} />
        ))
      )}

      {pending?.kind === "confirm" ? (
        <ActionDialog
          title={D.confirm}
          body={t(D.confirmBody, { amount: formatAmount(pending.dues.amount) })}
          confirmLabel={D.confirm}
          busy={busy}
          error={review.error?.message ?? null}
          onClose={close}
          onConfirm={run}
        />
      ) : null}
      {pending?.kind === "reject" ? (
        <ActionDialog
          title={D.rejectTitle}
          body={D.rejectBody}
          notesLabel={D.rejectLabel}
          notesRequired
          missingMessage={D.rejectMissing}
          confirmLabel={D.reject}
          confirmVariant="danger"
          busy={busy}
          error={review.error?.message ?? null}
          onClose={close}
          onConfirm={run}
        />
      ) : null}
      {pending?.kind === "cancel" ? (
        <ActionDialog
          title={D.cancel}
          body={D.cancelBody}
          notesLabel={D.cancelLabel}
          notesRequired
          missingMessage={D.cancelMissing}
          confirmLabel={D.cancel}
          confirmVariant="danger"
          busy={busy}
          error={cancel.error?.message ?? null}
          onClose={close}
          onConfirm={run}
        />
      ) : null}
    </section>
  );
}
