import type { ReferenceData } from "@/api/types";
import { ar, t } from "@/i18n/ar";

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
