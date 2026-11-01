import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { uploadDuesReceipt } from "@/api/endpoints/documents";
import { queryKeys } from "@/api/keys";
import type { DuesRequest, DuesRequestStatus, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { preCheckReceipt } from "@/features/documents/preCheck";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { formatAmount, formatDate } from "@/utils/format";
import { DuesStatusBadge } from "./DuesStatusBadge";

const D = ar.dues;
const OUTSTANDING = new Set<DuesRequestStatus>(["REQUESTED", "PENDING_REVIEW", "REJECTED"]);

const label = (choices: ReferenceData["duesRequestStatuses"] | undefined, value: string) =>
  choices?.find((choice) => choice.value === value)?.label ?? value;

/** «رفع إيصال السداد» for one request (allowed by the server: `can_upload_receipt`). */
function ReceiptUpload({ applicationId, dues }: { applicationId: string; dues: DuesRequest }) {
  const queryClient = useQueryClient();
  const reference = useReferenceData();
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();
  const [progress, setProgress] = useState(0);
  const [localError, setLocalError] = useState<string | null>(null);
  const limits = reference.data?.upload;
  const upload = useMutation({
    mutationFn: (file: File) => uploadDuesReceipt({ applicationId, duesId: dues.id, file }, setProgress),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.applications.detail(applicationId) }),
  });

  const handleFile = async (file: File | undefined) => {
    if (!file || !limits) return;
    upload.reset();
    const problem = await preCheckReceipt(file, limits);
    setLocalError(problem);
    if (problem) return;
    setProgress(0);
    upload.mutate(file);
  };

  const error = localError ?? (upload.isError ? upload.error.message : null);
  return (
    <div className="space-y-2">
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        aria-label={D.upload}
        aria-describedby={error ? errorId : undefined}
        accept={limits?.acceptedContentTypes.join(",")}
        disabled={upload.isPending}
        onChange={(event) => {
          void handleFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      <Button size="lg" onClick={() => inputRef.current?.click()} disabled={upload.isPending || !limits}>
        <Icon name="upload" className="size-5" />
        {D.upload}
      </Button>
      {upload.isPending ? <p className="text-sm text-slate">{t(D.uploading, { percent: progress })}</p> : null}
      {error ? (
        <p id={errorId} role="alert" className="font-semibold text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function StateLine({ dues }: { dues: DuesRequest }) {
  if (dues.status === "PENDING_REVIEW") {
    return (
      <div>
        <p className="font-extrabold text-status-submitted-fg">{D.statePending}</p>
        <p className="text-sm text-slate">{D.statePendingHint}</p>
      </div>
    );
  }
  if (dues.status === "REJECTED") {
    const last = dues.receipts.at(-1);
    return (
      <div>
        <p className="whitespace-pre-line font-extrabold text-status-rejected-fg">
          {t(D.stateRejected, { reason: last?.rejectionReason ?? "" })}
        </p>
        <p className="text-sm text-slate">{D.stateRejectedHint}</p>
      </div>
    );
  }
  return <p className="font-semibold text-charcoal">{D.stateRequested}</p>;
}

function OutstandingCard({ applicationId, dues, reference }: { applicationId: string; dues: DuesRequest; reference: ReferenceData | undefined }) {
  const historyId = useId();
  return (
    <article className="space-y-3 rounded-xl border border-warning/40 bg-white p-4">
      <div>
        <p className="text-sm font-bold text-slate">{D.amount}</p>
        <p className="text-3xl font-extrabold text-charcoal">
          <bdi>{formatAmount(dues.amount)}</bdi>
        </p>
      </div>
      <div>
        <p className="text-sm font-bold text-slate">{D.reason}</p>
        <p className="whitespace-pre-line text-charcoal" dir="auto">
          {dues.reason}
        </p>
        <p className="mt-1 text-xs text-muted">{t(D.requestedAt, { date: formatDate(dues.createdAt) })}</p>
      </div>
      <StateLine dues={dues} />
      {dues.canUploadReceipt ? <ReceiptUpload applicationId={applicationId} dues={dues} /> : null}
      {dues.receipts.length > 0 ? (
        <div>
          <h3 id={historyId} className="text-sm font-extrabold text-charcoal">
            {D.receipts}
          </h3>
          <ul aria-labelledby={historyId} className="mt-1 space-y-1">
            {dues.receipts.map((receipt) => (
              <li key={receipt.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate">{t(D.receiptAt, { date: formatDate(receipt.createdAt) })}</span>
                <DuesStatusBadge status={receipt.status} label={label(reference?.duesReceiptStatuses, receipt.status)} />
                <a
                  href={receipt.document.contentUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-bold text-teal-deep underline underline-offset-2"
                >
                  {t(D.view, { name: receipt.document.originalFilename })}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

/** Outstanding additional syndicate dues, shown prominently on the status page. */
export function OutstandingDues({ applicationId, requests }: { applicationId: string; requests: DuesRequest[] }) {
  const titleId = useId();
  const reference = useReferenceData();
  const outstanding = requests.filter((dues) => OUTSTANDING.has(dues.status));
  if (outstanding.length === 0) return null;
  return (
    <section aria-labelledby={titleId} className="space-y-3 rounded-2xl border-s-4 border-warning bg-banana-light p-4 sm:p-5">
      <h2 id={titleId} className="flex items-center gap-2 text-xl font-extrabold text-status-correction-fg">
        <Icon name="alert" className="size-6" />
        {D.outstandingTitle}
      </h2>
      <p className="text-charcoal">{D.outstandingIntro}</p>
      {outstanding.map((dues) => (
        <OutstandingCard key={dues.id} applicationId={applicationId} dues={dues} reference={reference.data} />
      ))}
    </section>
  );
}

/** Confirmed or cancelled requests, for the record. */
export function SettledDues({ requests }: { requests: DuesRequest[] }) {
  const titleId = useId();
  const reference = useReferenceData();
  const settled = requests.filter((dues) => !OUTSTANDING.has(dues.status));
  if (settled.length === 0) return null;
  return (
    <section aria-labelledby={titleId} className="rounded-xl border border-border bg-white p-4">
      <h2 id={titleId} className="font-extrabold text-charcoal">
        {D.settledTitle}
      </h2>
      <ul className="mt-2 space-y-2">
        {settled.map((dues) => (
          <li key={dues.id} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-bold text-charcoal">
              <bdi>{formatAmount(dues.amount)}</bdi>
            </span>
            <span className="min-w-0 flex-1 truncate text-slate" dir="auto">
              {dues.reason}
            </span>
            <DuesStatusBadge status={dues.status} label={label(reference.data?.duesRequestStatuses, dues.status)} />
          </li>
        ))}
      </ul>
    </section>
  );
}
