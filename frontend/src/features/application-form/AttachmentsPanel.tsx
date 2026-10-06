import { useId } from "react";
import { SmartUpload } from "@/features/documents/SmartUpload";
import { ar } from "@/i18n/ar";
import { useApplicationForm } from "./context";
import { useInlineErrors } from "./inlineErrors";

/**
 * Mandatory member attachments BEFORE the member fields so OCR can fill them (PROMPT.md §9.3).
 * Screen only. Slots and labels come from the server rules table (member, OCR-capable, form stage).
 */
export function AttachmentsPanel() {
  const titleId = useId();
  const { application, reference, memberDocuments, readOnly, documentsChanged, applyOcrSuggestions } =
    useApplicationForm();
  const inline = useInlineErrors();
  if (!application || !reference) return null;
  const slots = reference.documentRules.member.filter((slot) => slot.stage !== "submit" && slot.ocrCapable);

  return (
    <section
      aria-labelledby={titleId}
      className="rounded-xl border border-teal/30 bg-teal-light/40 p-3 sm:p-4 print:hidden"
    >
      <h2 id={titleId} className="font-extrabold text-charcoal">
        {ar.form.attachments.title}
      </h2>
      <p className="mt-1 text-sm text-slate">{ar.form.attachments.hint}</p>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
        {slots.map((slot) => (
          <div key={slot.type} className="flex min-w-0 flex-col">
            <SmartUpload
              applicationId={application.id}
              documentType={slot.type}
              label={slot.label}
              required={slot.required}
              document={memberDocuments[slot.type] ?? null}
              onUploaded={documentsChanged}
              ocrCapable={slot.ocrCapable}
              onExtracted={(fields) => applyOcrSuggestions(fields)}
              disabled={readOnly}
              className="flex-1"
            />
            {inline.memberDocuments[slot.type] ? (
              <p className="mt-1 text-sm font-semibold text-danger">{inline.memberDocuments[slot.type]}</p>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
