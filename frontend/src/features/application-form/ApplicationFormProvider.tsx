import type { ReactNode } from "react";
import { ApplicationFormContext } from "./context";
import type { DraftOptions } from "./draftController";
import { useApplicationDraft, type DraftPreset } from "./useApplicationDraft";

/** One draft per application page; key it by application id so a new id starts fresh. */
export function ApplicationFormProvider({
  applicationId,
  options,
  readOnly = false,
  preset,
  children,
}: {
  applicationId: string;
  options?: DraftOptions;
  /** Review and print show the sheet without editing, whatever the status. */
  readOnly?: boolean;
  /** Data from another endpoint (admin print); implies read-only. */
  preset?: DraftPreset;
  children: ReactNode;
}) {
  const draft = useApplicationDraft(applicationId, options, readOnly, preset);
  return <ApplicationFormContext.Provider value={draft}>{children}</ApplicationFormContext.Provider>;
}
