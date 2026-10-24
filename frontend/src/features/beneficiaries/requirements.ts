import type { Application, Beneficiary, DocumentRequirement, DocumentType } from "@/api/types";

/** `required_documents` is typed loosely by the schema; keep only well-formed slots. */
export function asRequirement(raw: Record<string, unknown>): DocumentRequirement | null {
  const { type, required, label, ocrCapable, stage, imagesOnly, hints } = raw;
  if (typeof type !== "string" || typeof label !== "string") return null;
  return {
    type: type as DocumentType,
    required: required === true,
    label,
    ocrCapable: ocrCapable === true,
    stage: stage === "submit" ? "submit" : "form",
    imagesOnly: imagesOnly === true,
    hints: Array.isArray(hints) ? hints.filter((hint): hint is string => typeof hint === "string") : [],
  };
}

const wellFormed = (slots: readonly Record<string, unknown>[]) =>
  slots.map(asRequirement).filter((slot): slot is DocumentRequirement => slot !== null);

/** The document slots of one beneficiary, straight from the server's rules table. */
export function requirementsOf(beneficiary: Beneficiary): DocumentRequirement[] {
  return wellFormed(beneficiary.requiredDocuments);
}

/**
 * The member slots of THIS application (server-evaluated: e.g. the member's own birth
 * certificate while a MOTHER is listed). Falls back to `fallback` (reference data) for payloads
 * that predate the field.
 */
export function memberRequirementsOf(
  application: Pick<Application, "memberRequiredDocuments"> | undefined,
  fallback: DocumentRequirement[] = [],
): DocumentRequirement[] {
  const slots = application?.memberRequiredDocuments;
  return Array.isArray(slots) ? wellFormed(slots) : fallback;
}

/** Every required slot has an active document (the paperclip turns green). */
export function documentsComplete(beneficiary: Beneficiary): boolean {
  const attached = new Set(beneficiary.documents.map((doc) => doc.documentType));
  return requirementsOf(beneficiary).every((slot) => !slot.required || attached.has(slot.type));
}
