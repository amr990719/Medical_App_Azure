import { createContext, useContext } from "react";
import type { DocumentType, ValidationResult } from "@/api/types";
import { useApplicationForm } from "./context";
import { fieldForPath } from "./mappers";
import type { BeneficiaryField, MemberField } from "./types";

/** Server validation errors placed under their fields (PROMPT.md §9.1: panel AND inline). */
export type InlineErrors = {
  member: Partial<Record<MemberField, string>>;
  rows: Record<number, Partial<Record<BeneficiaryField, string>>>;
  rowDocuments: Record<number, Partial<Record<DocumentType, string>>>;
  memberDocuments: Partial<Record<DocumentType, string>>;
};

export const NO_INLINE_ERRORS: InlineErrors = { member: {}, rows: {}, rowDocuments: {}, memberDocuments: {} };

export function buildInlineErrors(errors: ValidationResult["errors"]): InlineErrors {
  const result: InlineErrors = { member: {}, rows: {}, rowDocuments: {}, memberDocuments: {} };
  for (const error of errors) {
    const location = fieldForPath(error.field);
    switch (location.kind) {
      case "member":
        result.member[location.field] ??= error.message;
        break;
      case "row":
        (result.rows[location.index] ??= {})[location.field] ??= error.message;
        break;
      case "rowDocument":
        (result.rowDocuments[location.index] ??= {})[location.documentType] = error.message;
        break;
      case "memberDocument":
        result.memberDocuments[location.documentType] = error.message;
        break;
      default:
        break;
    }
  }
  return result;
}

export const InlineErrorsContext = createContext<InlineErrors>(NO_INLINE_ERRORS);

export const useInlineErrors = () => useContext(InlineErrorsContext);

/** The error to show under a member field: a refused save or ID hint first, then validation. */
export function useMemberError(field: MemberField): string | undefined {
  const { fieldErrors } = useApplicationForm();
  const inline = useInlineErrors();
  return fieldErrors[field] ?? inline.member[field];
}
