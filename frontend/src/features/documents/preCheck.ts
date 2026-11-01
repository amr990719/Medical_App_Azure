import type { ReferenceData } from "@/api/types";
import { ar, t } from "@/i18n/ar";
import { readImageSize } from "./imageSize";

const MEGABYTE = 1024 * 1024;

/**
 * Instant feedback before uploading (size and declared type), with the limits the server sends
 * in reference data. UX only: the server sniffs, decodes and re-checks every file.
 */
export function preCheckFile(file: File, upload: ReferenceData["upload"]): string | null {
  if (!upload.acceptedContentTypes.includes(file.type)) return ar.upload.unsupportedType;
  if (file.size > upload.maxBytes) {
    const max = t(ar.upload.megabytes, { value: Math.round((upload.maxBytes / MEGABYTE) * 10) / 10 });
    return t(ar.upload.tooLarge, { max });
  }
  return null;
}

type UploadLimits = ReferenceData["upload"];

/**
 * Receipts (the application's and the syndicate dues'): the file pre-check plus the minimum
 * receipt size (400×300). UX only; the server sniffs, decodes and measures again.
 */
export async function preCheckReceipt(file: File, upload: UploadLimits): Promise<string | null> {
  const problem = preCheckFile(file, upload);
  if (problem) return problem;
  const size = await readImageSize(file);
  if (!size) return ar.payment.unreadable;
  if (size.width < upload.receiptMinWidth || size.height < upload.receiptMinHeight) {
    return t(ar.payment.tooSmall, { width: upload.receiptMinWidth, height: upload.receiptMinHeight });
  }
  return null;
}

/**
 * Limits of one slot: image-only slots (personal photos, rules-table `images_only`) accept the
 * server's image list even when PDF documents are enabled.
 */
export function slotLimits(upload: UploadLimits | undefined, imagesOnly: boolean): UploadLimits | undefined {
  if (!upload || !imagesOnly) return upload;
  const images = upload.imageContentTypes ?? upload.acceptedContentTypes.filter((type) => type.startsWith("image/"));
  return { ...upload, acceptedContentTypes: images };
}
