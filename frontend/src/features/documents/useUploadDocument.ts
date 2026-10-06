import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { uploadDocument } from "@/api/endpoints/documents";
import type { DocumentSummary, DocumentType } from "@/api/types";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { preCheckFile } from "./preCheck";

/**
 * Upload on select for compact slots (photo box, checklist buttons): pre-check with the server's
 * limits, upload with progress, Arabic error. SmartUpload is the full slot with OCR.
 */
export function useUploadDocument({
  applicationId,
  documentType,
  beneficiaryId,
  imagesOnly = false,
  onUploaded,
}: {
  applicationId: string;
  documentType: DocumentType;
  beneficiaryId?: string | null;
  imagesOnly?: boolean;
  onUploaded: (document: DocumentSummary) => void;
}) {
  const reference = useReferenceData();
  const [progress, setProgress] = useState(0);
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (file: File) => uploadDocument({ applicationId, file, documentType, beneficiaryId }, setProgress),
    onSuccess: onUploaded,
  });
  const limits = reference.data?.upload;
  const types = limits?.acceptedContentTypes.filter((type) => !imagesOnly || type.startsWith("image/")) ?? [];

  const select = (file: File | undefined) => {
    if (!file || !limits) return;
    mutation.reset();
    const problem = preCheckFile(file, { ...limits, acceptedContentTypes: types });
    setLocalError(problem);
    if (problem) return;
    setProgress(0);
    mutation.mutate(file);
  };

  return {
    select,
    progress,
    isPending: mutation.isPending,
    error: localError ?? (mutation.isError ? mutation.error.message : null),
    accept: types.join(","),
    ready: Boolean(limits),
  };
}
