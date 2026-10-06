import type { DocumentSummary } from "@/api/types";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { Modal } from "@/components/ui/Modal";
import { ar, t } from "@/i18n/ar";
import { formatDate, formatFileSize } from "@/utils/format";

/**
 * Image types a browser shows inline. The server sends everything else (PDF, HEIC) as an
 * attachment with a sandbox CSP and X-Frame-Options DENY (`document_disposition`, Q-T17): an
 * uploaded file is never framed or rendered as a page inside the app.
 */
const INLINE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

/**
 * One document in a modal (PROMPT.md §44). `content_url` is the authorized, audited endpoint
 * (stream or ≤5-minute SAS redirect, D41) — never a permanent public URL.
 */
export function DocumentViewer({
  document,
  label,
  onClose,
}: {
  document: DocumentSummary | null;
  label: string;
  onClose: () => void;
}) {
  const inline = document ? INLINE_TYPES.has(document.contentType) : false;
  return (
    <Modal
      open={document !== null}
      title={label}
      onClose={onClose}
      size="lg"
      footer={
        document ? (
          <a href={document.contentUrl} target="_blank" rel="noopener noreferrer" className={buttonClasses("outline")}>
            {ar.admin.viewer.openNewTab}
          </a>
        ) : null
      }
    >
      {document ? (
        <figure className="space-y-3">
          <div className="grid min-h-64 place-items-center overflow-hidden rounded-lg border border-border bg-smoke">
            {inline ? (
              <img
                src={document.contentUrl}
                alt={t(ar.admin.viewer.imageAlt, { label })}
                className="max-h-[70dvh] w-auto max-w-full object-contain"
              />
            ) : (
              <div className="space-y-3 p-6 text-center">
                <p className="font-semibold text-charcoal">{ar.admin.viewer.notInline}</p>
                <a href={document.contentUrl} rel="noopener noreferrer" className={buttonClasses("primary")}>
                  {ar.admin.viewer.download}
                </a>
              </div>
            )}
          </div>
          <figcaption className="flex flex-wrap justify-between gap-2 text-sm text-slate">
            <bdi dir="ltr" className="truncate">
              {document.originalFilename}
            </bdi>
            <span>
              {formatFileSize(document.fileSize)} · {t(ar.admin.viewer.uploadedAt, { date: formatDate(document.createdAt) })}
            </span>
          </figcaption>
        </figure>
      ) : null}
    </Modal>
  );
}
