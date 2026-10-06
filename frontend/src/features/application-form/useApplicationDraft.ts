import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";
import { fetchApplication } from "@/api/endpoints/applications";
import { fetchProfile } from "@/api/endpoints/profile";
import { queryKeys } from "@/api/keys";
import type { Application, Beneficiary, DocumentSummary, DocumentType, DoctorProfile } from "@/api/types";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar } from "@/i18n/ar";
import { DraftController, type DraftOptions } from "./draftController";
import { parseNationalId } from "./nationalId";
import type { ApplicationFormState, MemberField } from "./types";

/** Instant national-ID consistency hints (§9.4); the server validation stays authoritative. */
function nationalIdErrors(state: ApplicationFormState | null): Partial<Record<MemberField, string>> {
  if (!state || state.nationalId.length !== 14) return {};
  const parsed = parseNationalId(state.nationalId);
  if (!parsed) return { nationalId: ar.form.errors.nationalIdInvalid };
  const errors: Partial<Record<MemberField, string>> = {};
  if (state.birthYear && Number(state.birthYear) !== parsed.birthYear) {
    errors.birthYear = ar.form.errors.birthYearMismatch;
  }
  if (state.gender && state.gender !== parsed.gender) errors.gender = ar.form.errors.genderMismatch;
  return errors;
}

/**
 * Port of the prototype's FormContext with the server as the source of truth (PROMPT.md §10):
 * loads application + profile + reference data, exposes the form state, the edit operations,
 * autosave status and the server documents of each row.
 */
/**
 * Data given by the caller instead of the doctor endpoints: the admin print view feeds the
 * sheet from GET /admin/applications/{id}/ (always read-only).
 */
export type DraftPreset = { application: Application; profile: DoctorProfile };

export function useApplicationDraft(
  applicationId: string,
  options: DraftOptions = {},
  forceReadOnly = false,
  preset?: DraftPreset,
) {
  const queryClient = useQueryClient();
  const reference = useReferenceData();
  const fetched = useQuery({
    queryKey: queryKeys.applications.detail(applicationId),
    queryFn: () => fetchApplication(applicationId),
    enabled: !preset,
  });
  const fetchedProfile = useQuery({ queryKey: queryKeys.profile, queryFn: fetchProfile, enabled: !preset });
  const application = preset ? { data: preset.application, error: null, refetch: fetched.refetch } : fetched;
  const profile = preset ? { data: preset.profile, error: null, refetch: fetchedProfile.refetch } : fetchedProfile;
  const [controller] = useState(() => new DraftController(queryClient, applicationId, options));
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot);

  const maxRows = reference.data?.maxBeneficiaries;
  useEffect(() => {
    if (application.data && profile.data && maxRows) {
      controller.initialize(application.data, profile.data, maxRows, forceReadOnly || Boolean(preset));
    }
  }, [controller, application.data, profile.data, maxRows, forceReadOnly, preset]);

  // Leaving the page sends what the debounce was still holding.
  useEffect(() => () => controller.release(), [controller]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!controller.getSnapshot().isDirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [controller]);

  const app = application.data;
  const rows = snapshot.state?.beneficiaries ?? [];
  const rowServer = (index: number): Beneficiary | undefined => {
    const id = rows[index]?.id;
    return id ? app?.beneficiaries.find((b) => b.id === id) : undefined;
  };
  const memberDocuments: Partial<Record<DocumentType, DocumentSummary>> = {};
  for (const doc of app?.documents ?? []) {
    if (!doc.beneficiaryId) memberDocuments[doc.documentType] = doc;
  }

  return {
    isLoading: !snapshot.state && !application.error && !profile.error && !reference.error,
    loadError: application.error ?? profile.error ?? reference.error ?? null,
    reload: () => {
      void application.refetch();
      void profile.refetch();
      void reference.refetch();
    },
    application: app,
    reference: reference.data,
    state: snapshot.state,
    readOnly: snapshot.readOnly,
    saveStatus: snapshot.saveStatus,
    isDirty: snapshot.isDirty,
    fieldErrors: { ...nationalIdErrors(snapshot.state), ...snapshot.fieldErrors },
    rowErrors: snapshot.rowErrors,
    pendingDeletion: snapshot.pendingDeletion,
    memberDocuments,
    rowServer,
    updateField: controller.updateField,
    updateBeneficiary: controller.updateBeneficiary,
    updateBeneficiaryBatch: controller.updateBeneficiaryBatch,
    applyOcrSuggestions: controller.applyOcrSuggestions,
    clearRow: controller.clearRow,
    confirmDeletion: controller.confirmDeletion,
    cancelDeletion: controller.cancelDeletion,
    flush: controller.flush,
    retrySave: controller.retry,
    /** A document was uploaded or removed: refetch the application (documents, validation). */
    documentsChanged: () =>
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.detail(applicationId) }),
  };
}

export type ApplicationDraft = ReturnType<typeof useApplicationDraft>;
