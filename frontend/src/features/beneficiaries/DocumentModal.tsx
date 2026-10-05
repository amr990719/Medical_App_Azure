import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/api/keys";
import type { Beneficiary, DocumentRequirement, DocumentType } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { SmartUpload } from "@/features/documents/SmartUpload";
import { ar, t } from "@/i18n/ar";

/** `required_documents` is typed loosely by the schema; keep only well-formed slots. */
function asRequirement(raw: Record<string, unknown>): DocumentRequirement | null {
  const { type, required, label, ocrCapable } = raw;
  if (typeof type !== "string" || typeof label !== "string") return null;
  return {
    type: type as DocumentType,
    required: required === true,
    label,
    ocrCapable: ocrCapable === true,
  };
}

export interface DocumentModalProps {
  open: boolean;
  applicationId: string;
  beneficiary: Beneficiary;
  onClose: () => void;
  readOnly?: boolean;
}

/**
 * Documents of one beneficiary (PROMPT.md §11): one slot per document the server's rules table
 * requires or allows for this kinship and age. Each upload is saved immediately; closing is safe.
 * OCR on the capable slots is added in Session 5.
 */
export function DocumentModal({ open, applicationId, beneficiary, onClose, readOnly = false }: DocumentModalProps) {
  const queryClient = useQueryClient();
  const requirements = beneficiary.requiredDocuments
    .map(asRequirement)
    .filter((slot): slot is DocumentRequirement => slot !== null);

  const name = beneficiary.fullName.trim() || ar.documents.unnamedBeneficiary;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={t(ar.documents.modalTitle, { name })}
      footer={<Button onClick={onClose}>{ar.documents.saveAndClose}</Button>}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {requirements.map((slot) => (
          <SmartUpload
            key={slot.type}
            applicationId={applicationId}
            beneficiaryId={beneficiary.id}
            documentType={slot.type}
            label={slot.label}
            required={slot.required}
            disabled={readOnly}
            document={beneficiary.documents.find((doc) => doc.documentType === slot.type) ?? null}
            onUploaded={() => {
              void queryClient.invalidateQueries({ queryKey: queryKeys.applications.detail(applicationId) });
            }}
          />
        ))}
      </div>
    </Modal>
  );
}
