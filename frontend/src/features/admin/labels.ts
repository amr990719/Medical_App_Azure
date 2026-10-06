import type { Choice, DocumentType, ReferenceData } from "@/api/types";

/** Arabic label of an enum value from reference data; the raw value when it is unknown. */
export function choiceLabel(choices: readonly Choice[] | undefined, value: string | null | undefined): string {
  if (!value) return "";
  return choices?.find((choice) => choice.value === value)?.label ?? value;
}

export function documentTypeLabel(reference: ReferenceData | undefined, type: DocumentType): string {
  return reference?.documentRules.documentTypes.find((doc) => doc.type === type)?.label ?? type;
}
