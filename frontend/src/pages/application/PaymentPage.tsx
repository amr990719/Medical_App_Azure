import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState, type DragEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { deleteDocument, uploadDocument } from "@/api/endpoints/documents";
import { queryKeys } from "@/api/keys";
import type { DocumentSummary } from "@/api/types";
import { StickyActionBar } from "@/components/form/StickyActionBar";
import { Button } from "@/components/ui/Button";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { useApplication } from "@/features/applications/useApplication";
import { completedSteps, useValidation } from "@/features/applications/useValidation";
import { readImageSize } from "@/features/documents/imageSize";
import { preCheckFile } from "@/features/documents/preCheck";
import { FeeSummaryPanel } from "@/features/fees/FeeSummaryPanel";
import { useFeeQuote } from "@/features/fees/useFeeQuote";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { WizardFrame } from "@/layouts/WizardFrame";
import { cx } from "@/utils/cx";
import { formatFileSize } from "@/utils/format";

const P = ar.payment;

/** Drop zone + uploaded bar for PAYMENT_RECEIPT (port of the prototype's ReceiptPage). */
function ReceiptUpload({
  applicationId,
  receipt,
  paymentStatus,
}: {
  applicationId: string;
  receipt: DocumentSummary | undefined;
  paymentStatus: string;
}) {
  const queryClient = useQueryClient();
  const reference = useReferenceData();
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();
  const barId = useId();
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const limits = reference.data?.upload;

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.applications.detail(applicationId) });
  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadDocument({ applicationId, file, documentType: "PAYMENT_RECEIPT" }, setProgress),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: refresh,
  });

  const handleFile = async (file: File | undefined) => {
    if (!file || !limits) return;
    upload.reset();
    // UX pre-check (type, size, 400×300); the server sniffs, decodes and checks again.
    let problem = preCheckFile(file, limits);
    if (!problem) {
      const size = await readImageSize(file);
      if (!size) problem = P.unreadable;
      else if (size.width < limits.receiptMinWidth || size.height < limits.receiptMinHeight) {
        problem = t(P.tooSmall, { width: limits.receiptMinWidth, height: limits.receiptMinHeight });
      }
    }
    setLocalError(problem);
    if (problem) return;
    setProgress(0);
    upload.mutate(file);
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragging(false);
    void handleFile(event.dataTransfer.files[0]);
  };

  const error = localError ?? (upload.isError ? upload.error.message : null) ?? (remove.isError ? remove.error.message : null);
  const paymentLabel = (status: string) =>
    reference.data?.paymentStatuses.find((choice) => choice.value === status)?.label ?? status;
  const max = limits ? formatFileSize(limits.maxBytes) : "";

  return (
    <section className="space-y-3">
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-label={P.title}
        aria-describedby={error ? errorId : undefined}
        accept={limits?.acceptedContentTypes.join(",")}
        onChange={(event) => {
          void handleFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      {receipt ? (
        <div
          role="group"
          aria-labelledby={barId}
          className="flex flex-wrap items-center gap-3 rounded-xl border border-teal/40 bg-white p-3"
        >
          <span id={barId} className="sr-only">
            {P.uploadedLabel}
          </span>
          <div className="grid size-14 shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-smoke">
            {receipt.contentType.startsWith("image/") ? (
              <img
                src={receipt.contentUrl}
                alt={t(ar.upload.preview, { name: receipt.originalFilename })}
                className="size-full object-cover"
              />
            ) : (
              <Icon name="file" className="text-muted" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-bold text-charcoal" dir="auto">
              {receipt.originalFilename}
            </p>
            <p className="text-sm text-slate">
              {formatFileSize(receipt.fileSize)}
              {" · "}
              <span>{t(P.status, { status: paymentLabel(paymentStatus) })}</span>
            </p>
          </div>
          <Button variant="ghost" className="text-danger hover:bg-danger-light" disabled={remove.isPending} onClick={() => remove.mutate(receipt.id)}>
            {ar.upload.remove}
          </Button>
          <Button variant="outline" disabled={upload.isPending || !limits} onClick={() => inputRef.current?.click()}>
            {ar.upload.replace}
          </Button>
        </div>
      ) : (
        <button
          type="button"
          disabled={!limits || upload.isPending}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cx(
            "flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-10 text-center transition-colors",
            dragging ? "border-teal bg-teal-light" : "border-border-hover bg-white hover:border-teal hover:bg-teal-light/40",
          )}
        >
          <span className="grid size-14 place-items-center rounded-full bg-banana-light text-charcoal">
            <Icon name="upload" className="size-7" />
          </span>
          <span className="text-lg font-extrabold text-charcoal">{P.drop}</span>
          <span className="font-semibold text-teal-deep">{P.orClick}</span>
          {limits ? (
            <span className="text-sm text-muted" dir="rtl">
              {t(P.accepted, { max, width: limits.receiptMinWidth, height: limits.receiptMinHeight })}
            </span>
          ) : null}
        </button>
      )}
      {upload.isPending ? (
        <div
          role="progressbar"
          aria-label={P.title}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
          className="h-2 overflow-hidden rounded-full bg-border"
        >
          <div className="h-full rounded-full bg-teal transition-[width]" style={{ width: `${progress}%` }} />
        </div>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="font-semibold text-danger">
          {error}
        </p>
      ) : null}
    </section>
  );
}

/** `/application/:id/payment` — step 4: fee summary + payment receipt (PROMPT.md §18). */
export function PaymentPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const application = useApplication(id);
  const validation = useValidation(id);
  const fees = useFeeQuote(id);

  if (application.error) {
    return <FullPageStatus isError message={application.error.message} onRetry={() => void application.refetch()} />;
  }
  const app = application.data;
  if (!app) return <FullPageStatus message={ar.common.loading} />;
  if (!app.isEditable) return <Navigate to={`/application/${id}/status`} replace />;

  const receipt = app.documents.find((doc) => doc.documentType === "PAYMENT_RECEIPT");

  return (
    <WizardFrame applicationId={id} fiscalYear={app.fiscalYear} step={4} completed={completedSteps(validation.data?.stepsComplete)}>
      <div className="mx-auto max-w-[720px] space-y-5 px-3 pb-36 pt-5 sm:px-4">
        <Link
          to={`/application/${id}/form`}
          className="inline-flex items-center gap-1.5 rounded-lg font-bold text-teal-deep hover:underline"
        >
          <Icon name="arrow" mirror className="size-4 rotate-180" />
          {P.back}
        </Link>
        <h1 className="text-2xl font-extrabold text-charcoal">{P.title}</h1>
        <FeeSummaryPanel quote={fees.data} isLoading={fees.isLoading} error={fees.error} accent="banana" />
        <section className="rounded-xl border border-border bg-white p-5">
          <h2 className="font-extrabold text-charcoal">{P.instructionsTitle}</h2>
          <p className="mt-1 text-slate">{P.instructions}</p>
        </section>
        <ReceiptUpload applicationId={id} receipt={receipt} paymentStatus={app.paymentStatus} />
        {!receipt ? <p className="text-sm text-muted">{P.needReceipt}</p> : null}
      </div>
      <StickyActionBar
        label={ar.form.actionsLabel}
        end={
          <Button disabled={!receipt} onClick={() => navigate(`/application/${id}/review`)}>
            {P.continue}
            <Icon name="arrow" mirror className="size-4" />
          </Button>
        }
      />
    </WizardFrame>
  );
}
