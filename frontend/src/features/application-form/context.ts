import { createContext, useContext } from "react";
import type { ApplicationDraft } from "./useApplicationDraft";

export const ApplicationFormContext = createContext<ApplicationDraft | null>(null);

/** The draft of the surrounding ApplicationFormProvider. */
export function useApplicationForm(): ApplicationDraft {
  const draft = useContext(ApplicationFormContext);
  if (!draft) throw new Error("useApplicationForm must be used inside ApplicationFormProvider");
  return draft;
}
