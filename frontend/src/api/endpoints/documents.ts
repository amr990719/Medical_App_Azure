import { apiFetch, apiUpload } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type { DocumentSummary, DocumentType } from "../types";

export type UploadInput = {
  applicationId: string;
  file: File;
  documentType: DocumentType;
  beneficiaryId?: string | null;
};

/** Upload on select (PROMPT.md §10.3): the server validates, stores in Blob and returns metadata. */
export async function uploadDocument(
  { applicationId, file, documentType, beneficiaryId }: UploadInput,
  onProgress?: (percent: number) => void,
): Promise<DocumentSummary> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("document_type", documentType);
  if (beneficiaryId) form.append("beneficiary_id", beneficiaryId);
  const result = await apiUpload<components["schemas"]["DocumentSummary"]>(
    `/applications/${applicationId}/documents/`,
    form,
    onProgress,
  );
  return toCamel(result);
}

export async function deleteDocument(id: string): Promise<void> {
  await apiFetch<undefined>(`/documents/${id}/`, { method: "DELETE" });
}
