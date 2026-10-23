import { useQueryClient } from "@tanstack/react-query";
import { useId } from "react";
import { queryKeys } from "@/api/keys";
import type { OcrFields } from "@/api/endpoints/documents";
import type { Beneficiary, DocumentRequirement, DocumentSummary, DocumentType } from "@/api/types";
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
  /** OCR suggestions of a capable slot (national ID front, birth certificate) for this row. */
  onExtracted?: (fields: OcrFields) => void;
  /**
   * Member-owned slots that this beneficiary makes necessary (the member's own birth
   * certificate for a MOTHER). Uploaded WITHOUT a beneficiary and never OCR'd into this row.
   */
  memberSlots?: DocumentRequirement[];
  memberDocuments?: Partial<Record<DocumentType, DocumentSummary>>;
}

/**
 * Documents of one beneficiary (PROMPT.md §11): one slot per document the server's rules table
 * requires or allows for this kinship, age and first-time answer — each national-ID side is its
 * own slot. Each upload is saved immediately; closing is safe. OCR-capable slots offer
 * `مسح تلقائي`; the suggestions fill only this row's empty fields.
 */
export function DocumentModal({
  open,
  applicationId,
  beneficiary,
  onClose,
  readOnly = false,
  onExtracted,
  memberSlots = [],
  memberDocuments = {},
}: DocumentModalProps) {
  const queryClient = useQueryClient();
  const memberTitleId = useId();
  const requirements = requirementsOf(beneficiary);
  // The detail key prefixes the fee quote and validation, so both refresh too.
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: queryKeys.applications.detail(applicationId) });

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
            imagesOnly={slot.imagesOnly}
            hints={slot.hints}
            onExtracted={onExtracted}
            document={beneficiary.documents.find((doc) => doc.documentType === slot.type) ?? null}
            onUploaded={refresh}
          />
        ))}
      </div>
      {memberSlots.length > 0 ? (
        <section aria-labelledby={memberTitleId} className="mt-4 border-t border-border pt-4">
          <h3 id={memberTitleId} className="font-extrabold text-charcoal">
            {ar.documents.memberSection}
          </h3>
          <p className="mb-3 text-sm text-slate">{ar.documents.memberSectionHint}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {memberSlots.map((slot) => (
              <SmartUpload
                key={slot.type}
                applicationId={applicationId}
                beneficiaryId={null}
                documentType={slot.type}
                label={slot.label}
                required={slot.required}
                disabled={readOnly}
                imagesOnly={slot.imagesOnly}
                hints={slot.hints}
                document={memberDocuments[slot.type] ?? null}
                onUploaded={refresh}
              />
            ))}
          </div>
        </section>
      ) : null}
    </Modal>
  );
}
