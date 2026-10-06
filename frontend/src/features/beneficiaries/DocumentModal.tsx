import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/api/keys";
import type { OcrFields } from "@/api/endpoints/documents";
import type { Beneficiary } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { SmartUpload } from "@/features/documents/SmartUpload";
import { ar, t } from "@/i18n/ar";
import { requirementsOf } from "./requirements";

export interface DocumentModalProps {
  open: boolean;
  applicationId: string;
  beneficiary: Beneficiary;
  onClose: () => void;
  readOnly?: boolean;
  /** OCR suggestions of a capable slot (national ID, birth certificate) for this row. */
  onExtracted?: (fields: OcrFields) => void;
}

/**
 * Documents of one beneficiary (PROMPT.md §11): one slot per document the server's rules table
 * requires or allows for this kinship and age. Each upload is saved immediately; closing is safe.
 * OCR-capable slots offer `مسح تلقائي`; the suggestions fill only this row's empty fields.
 */
export function DocumentModal({
  open,
  applicationId,
  beneficiary,
  onClose,
  readOnly = false,
  onExtracted,
}: DocumentModalProps) {
  const queryClient = useQueryClient();
  const requirements = requirementsOf(beneficiary);

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
            ocrCapable={slot.ocrCapable}
            onExtracted={onExtracted}
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
