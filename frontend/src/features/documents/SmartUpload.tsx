import { useMutation } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { uploadDocument } from "@/api/endpoints/documents";
import type { DocumentSummary, DocumentType } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { preCheckFile } from "./preCheck";

export interface SmartUploadProps {
  applicationId: string;
  documentType: DocumentType;
  beneficiaryId?: string | null;
  label: string;
  required: boolean;
  /** The document already stored in this slot, if any. */
  document: DocumentSummary | null;
  onUploaded: (document: DocumentSummary) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * One document slot (PROMPT.md §11): upload on select with progress, thumbnail through the
 * authorized content URL, server error messages in Arabic. OCR ("مسح تلقائي") joins in Session 5.
 */
export function SmartUpload({
  applicationId,
  documentType,
  beneficiaryId,
  label,
  required,
  document,
  onUploaded,
  disabled = false,
  className,
}: SmartUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();
  const reference = useReferenceData();
  const [progress, setProgress] = useState(0);
  const [localError, setLocalError] = useState<string | null>(null);
  const [current, setCurrent] = useState<DocumentSummary | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadDocument({ applicationId, file, documentType, beneficiaryId }, setProgress),
    onSuccess: (stored) => {
      setCurrent(stored);
      onUploaded(stored);
    },
  });

  const shown = current ?? document;
  const error = localError ?? (upload.isError ? upload.error.message : null);
  const limits = reference.data?.upload;

  const handleFile = (file: File | undefined) => {
    if (!file || !limits) return;
    upload.reset();
    const problem = preCheckFile(file, limits);
    setLocalError(problem);
    if (problem) return;
    setProgress(0);
    upload.mutate(file);
  };

  return (
    <fieldset
      className={cx(
        "relative flex min-w-0 flex-col gap-3 rounded-xl border bg-white p-4",
        shown ? "border-teal/50" : "border-dashed border-border-hover",
        error && "border-danger/60",
        className,
      )}
    >
      {/* First child, floated into the flow: the legend names the slot for assistive tech. */}
      <legend className="float-start w-full pe-20 font-bold text-charcoal">{label}</legend>
      <span
        className={cx(
          "absolute end-4 top-4 rounded-full px-2 py-0.5 text-xs font-bold",
          required ? "bg-banana-light text-status-submitted-fg" : "bg-smoke text-muted",
        )}
      >
        {required ? ar.common.required : ar.common.optional}
      </span>

      <div className="clear-both flex items-center gap-3">
        <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-smoke">
          {shown && shown.contentType.startsWith("image/") ? (
            <img
              src={shown.contentUrl}
              alt={t(ar.upload.preview, { name: shown.originalFilename })}
              className="size-full object-cover"
            />
          ) : (
            <Icon name={shown ? "file" : "upload"} className="size-6 text-muted" />
          )}
        </div>
        <div className="min-w-0 flex-1 text-sm">
          {upload.isPending ? (
            <div>
              <p className="text-slate">{t(ar.upload.uploading, { percent: progress })}</p>
              <div
                role="progressbar"
                aria-label={label}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
                className="mt-1 h-2 overflow-hidden rounded-full bg-border"
              >
                <div className="h-full rounded-full bg-teal transition-[width]" style={{ width: `${progress}%` }} />
              </div>
            </div>
          ) : shown ? (
            <p className="break-all font-semibold text-teal-deep">
              {t(ar.upload.attached, { name: shown.originalFilename })}
            </p>
          ) : null}
          {error ? (
            <p id={errorId} role="alert" className="mt-1 font-semibold text-danger">
              {error}
            </p>
          ) : null}
        </div>
      </div>

      <div>
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          tabIndex={-1}
          aria-label={label}
          aria-describedby={error ? errorId : undefined}
          accept={limits?.acceptedContentTypes.join(",")}
          disabled={disabled || upload.isPending}
          onChange={(event) => {
            handleFile(event.target.files?.[0]);
            event.target.value = ""; // choosing the same file again still triggers a change
          }}
        />
        <Button
          variant="outline"
          disabled={disabled || upload.isPending || !limits}
          onClick={() => inputRef.current?.click()}
        >
          <Icon name="upload" className="size-4" />
          {shown ? ar.upload.replace : ar.upload.choose}
        </Button>
      </div>
    </fieldset>
  );
}
