import type { Beneficiary, DocumentRequirement, DocumentType } from "@/api/types";

/** `required_documents` is typed loosely by the schema; keep only well-formed slots. */
function asRequirement(raw: Record<string, unknown>): DocumentRequirement | null {
  const { type, required, label, ocrCapable } = raw;
  if (typeof type !== "string" || typeof label !== "string") return null;
  return { type: type as DocumentType, required: required === true, label, ocrCapable: ocrCapable === true };
}

/** The document slots of one beneficiary, straight from the server's rules table. */
export function requirementsOf(beneficiary: Beneficiary): DocumentRequirement[] {
  return beneficiary.requiredDocuments.map(asRequirement).filter((slot): slot is DocumentRequirement => slot !== null);
}

/** Every required slot has an active document (the paperclip turns green). */
export function documentsComplete(beneficiary: Beneficiary): boolean {
  const attached = new Set(beneficiary.documents.map((doc) => doc.documentType));
  return requirementsOf(beneficiary).every((slot) => !slot.required || attached.has(slot.type));
}
