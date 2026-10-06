/**
 * Autosave engine of the paper form (PROMPT.md §10.3), kept outside React so that timers,
 * in-flight requests and the "last saved" copy never depend on render timing.
 *
 * - Edits change local state immediately; after `debounceMs` of quiet, ONE save cycle sends only
 *   the fields that changed, to the resource that owns them (profile, application, beneficiary).
 * - Values still being typed (7 of 14 national-ID digits, a 3-digit year) stay local until complete.
 * - Network / 5xx failures retry with backoff (1 s, 2 s, 4 s) then report "error"; 4xx field errors
 *   are shown inline and the other fields of the same request are re-sent without them.
 * - Nothing typed is ever dropped: a field stays dirty until the server acknowledged that value.
 */
import type { QueryClient } from "@tanstack/react-query";
import { updateApplication } from "@/api/endpoints/applications";
import { createBeneficiary, deleteBeneficiary, updateBeneficiary } from "@/api/endpoints/beneficiaries";
import type { OcrFields } from "@/api/endpoints/documents";
import { updateProfile } from "@/api/endpoints/profile";
import { ApiError } from "@/api/client";
import { queryKeys } from "@/api/keys";
import type { Application, Beneficiary, DoctorProfile } from "@/api/types";
import {
  applicationPatch,
  isApplicationField,
  isProfileField,
  isSendable,
  memberFieldErrors,
  mergeMemberOcr,
  mergeRowOcr,
  profilePatch,
  rowFieldErrors,
  rowPatch,
  toFormState,
} from "./mappers";
import { parseNationalId } from "./nationalId";
import {
  emptyRow,
  type ApplicationFormState,
  type BeneficiaryField,
  type BeneficiaryRow,
  type MemberField,
  type MemberFields,
  type SaveStatus,
} from "./types";

export type DraftOptions = { debounceMs?: number; retryDelays?: readonly number[] };

/** PROMPT.md §10.3 timings: ~800 ms debounce, backoff 1 s / 2 s / 4 s. Tests shorten them. */
export const draftDefaults: { debounceMs: number; retryDelays: readonly number[] } = {
  debounceMs: 800,
  retryDelays: [1000, 2000, 4000],
};

export type RowErrors = Record<number, Partial<Record<BeneficiaryField, string>>>;

export type DraftSnapshot = {
  state: ApplicationFormState | null;
  saved: ApplicationFormState | null;
  saveStatus: SaveStatus;
  fieldErrors: Partial<Record<MemberField, string>>;
  rowErrors: RowErrors;
  pendingDeletion: number | null;
  isDirty: boolean;
  readOnly: boolean;
};

const MEMBER_KEYS: MemberField[] = [
  "applicationType", "syndicateType", "subSyndicate", "registrationNumber", "treatmentCardNumber",
  "syndicateRegistrationYear", "workStatus", "memberName", "religion", "nationalId", "gender",
  "birthYear", "governorate", "neighborhood", "address", "mobile", "declarationName",
];
const ROW_KEYS: BeneficiaryField[] = ["kinship", "name", "birthYear", "nationalId"];

const isEmptyRow = (row: BeneficiaryRow) => ROW_KEYS.every((key) => row[key] === "");
/** A stored row whose name and kinship were cleared: waiting for the deletion confirmation. */
const isClearedStoredRow = (row: BeneficiaryRow) => Boolean(row.id) && !row.name.trim() && row.kinship === "";

const retryable = (error: unknown) => error instanceof ApiError && (error.status === 0 || error.status >= 500);

function computeDirty(state: ApplicationFormState | null, saved: ApplicationFormState | null): boolean {
  if (!state || !saved) return false;
  if (MEMBER_KEYS.some((key) => state[key] !== saved[key])) return true;
  return state.beneficiaries.some((row, index) => {
    const before = saved.beneficiaries[index] ?? emptyRow();
    return ROW_KEYS.some((key) => row[key] !== before[key]);
  });
}

/** Birth year and gender follow a valid national ID when they are still empty (§9.4). */
function withNationalIdDefaults<S extends MemberFields>(state: S): S {
  const parsed = parseNationalId(state.nationalId);
  if (!parsed) return state;
  return {
    ...state,
    birthYear: state.birthYear || String(parsed.birthYear),
    gender: state.gender || parsed.gender,
  };
}

type Failure = { retry: boolean };

export class DraftController {
  private readonly listeners = new Set<() => void>();
  private readonly debounceMs: number;
  private readonly retryDelays: readonly number[];
  private snapshot: DraftSnapshot = {
    state: null,
    saved: null,
    saveStatus: "idle",
    fieldErrors: {},
    rowErrors: {},
    pendingDeletion: null,
    isDirty: false,
    readOnly: true,
  };
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running: Promise<void> | null = null;
  private rerun = false;
  private attempt = 0;

  constructor(
    private readonly queryClient: QueryClient,
    private readonly applicationId: string,
    options: DraftOptions = {},
  ) {
    this.debounceMs = options.debounceMs ?? draftDefaults.debounceMs;
    this.retryDelays = options.retryDelays ?? draftDefaults.retryDelays;
  }

  // ---- store plumbing (useSyncExternalStore) ----------------------------------------------

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = () => this.snapshot;

  private set(patch: Partial<DraftSnapshot>) {
    const next = { ...this.snapshot, ...patch };
    next.isDirty = computeDirty(next.state, next.saved);
    this.snapshot = next;
    this.listeners.forEach((listener) => listener());
  }

  // ---- lifecycle -----------------------------------------------------------------------------

  /** First load builds the form from the server; later calls only follow the editable flag. */
  initialize(app: Application, profile: DoctorProfile, maxRows: number, forceReadOnly = false) {
    const readOnly = forceReadOnly || !app.isEditable;
    if (this.snapshot.state) {
      if (readOnly !== this.snapshot.readOnly) this.set({ readOnly });
      return;
    }
    const state = toFormState(app, profile, maxRows);
    this.set({ state, saved: state, readOnly });
  }

  /** Stop the debounce timer and send what is pending right away (leaving the page). */
  release() {
    if (this.timer !== undefined && this.snapshot.isDirty) void this.flush();
  }

  // ---- edits ---------------------------------------------------------------------------------

  updateField = (field: MemberField, value: string) => {
    const { state, readOnly } = this.snapshot;
    if (!state || readOnly || field === "email") return;
    let next: ApplicationFormState = { ...state, [field]: value };
    if (field === "nationalId") next = withNationalIdDefaults(next);
    const fieldErrors = { ...this.snapshot.fieldErrors, [field]: undefined };
    this.set({ state: next, fieldErrors });
    this.schedule();
  };

  updateBeneficiary = (index: number, field: BeneficiaryField, value: string) => {
    this.updateBeneficiaryBatch(index, { [field]: value });
  };

  updateBeneficiaryBatch = (index: number, changes: Partial<Omit<BeneficiaryRow, "id">>) => {
    const { state, readOnly } = this.snapshot;
    const current = state?.beneficiaries[index];
    if (!state || !current || readOnly) return;
    const row = { ...current, ...changes };
    if (row.id && changes.kinship !== undefined && changes.kinship !== current.kinship) {
      // The required set changed: the server removes this row's documents (§9.5). Mirror it now
      // so the paperclip turns grey without waiting for the response.
      this.patchCachedBeneficiary(row.id, (b) => ({ ...b, documents: [] }));
    }
    const beneficiaries = state.beneficiaries.map((r, i) => (i === index ? row : r));
    const rowErrors = { ...this.snapshot.rowErrors };
    const previousErrors = rowErrors[index];
    if (previousErrors) {
      const cleared = Object.fromEntries(Object.keys(changes).map((key) => [key, undefined]));
      rowErrors[index] = { ...previousErrors, ...cleared };
    }
    this.set({
      state: { ...state, beneficiaries },
      rowErrors,
      pendingDeletion: isClearedStoredRow(row) ? index : this.snapshot.pendingDeletion,
    });
    this.schedule();
  };

  /**
   * Merge OCR suggestions into EMPTY fields only (member, or one beneficiary row).
   * Returns how many fields were filled.
   */
  applyOcrSuggestions = (fields: OcrFields, rowIndex?: number): number => {
    const { state, readOnly } = this.snapshot;
    if (!state || readOnly) return 0;
    if (rowIndex === undefined) {
      const { next, filled } = mergeMemberOcr(state, fields);
      if (filled.length === 0) return 0;
      this.set({ state: filled.includes("nationalId") ? withNationalIdDefaults(next) : next });
      this.schedule();
      return filled.length;
    }
    const row = state.beneficiaries[rowIndex];
    if (!row) return 0;
    const { next, filled } = mergeRowOcr(row, fields);
    if (filled.length === 0) return 0;
    this.updateBeneficiaryBatch(rowIndex, next);
    return filled.length;
  };

  /** Explicit "clear row": a stored row is deleted only after confirmation. */
  clearRow = (index: number) => {
    const { state, readOnly } = this.snapshot;
    const row = state?.beneficiaries[index];
    if (!state || !row || readOnly) return;
    const cleared = { ...emptyRow(), id: row.id };
    const beneficiaries = state.beneficiaries.map((r, i) => (i === index ? (row.id ? cleared : emptyRow()) : r));
    this.set({ state: { ...state, beneficiaries }, pendingDeletion: row.id ? index : this.snapshot.pendingDeletion });
    if (!row.id) this.schedule();
  };

  cancelDeletion = () => {
    const { state, saved, pendingDeletion } = this.snapshot;
    if (!state || !saved || pendingDeletion === null) return;
    const before = saved.beneficiaries[pendingDeletion] ?? emptyRow();
    const beneficiaries = state.beneficiaries.map((r, i) => (i === pendingDeletion ? { ...before } : r));
    this.set({ state: { ...state, beneficiaries }, pendingDeletion: null });
  };

  confirmDeletion = async () => {
    const { state, pendingDeletion } = this.snapshot;
    const id = pendingDeletion === null ? undefined : state?.beneficiaries[pendingDeletion]?.id;
    if (pendingDeletion === null || !id) return;
    try {
      await deleteBeneficiary(this.applicationId, id);
    } catch {
      this.cancelDeletion();
      this.set({ saveStatus: "error" });
      return;
    }
    const replace = (rows: BeneficiaryRow[]) => rows.map((r, i) => (i === pendingDeletion ? emptyRow() : r));
    const current = this.snapshot;
    if (current.state && current.saved) {
      this.set({
        state: { ...current.state, beneficiaries: replace(current.state.beneficiaries) },
        saved: { ...current.saved, beneficiaries: replace(current.saved.beneficiaries) },
        pendingDeletion: null,
        saveStatus: "saved",
      });
    }
    this.queryClient.setQueryData<Application>(queryKeys.applications.detail(this.applicationId), (old) =>
      old ? { ...old, beneficiaries: old.beneficiaries.filter((b) => b.id !== id) } : old,
    );
    this.invalidateDerived();
  };

  // ---- saving --------------------------------------------------------------------------------

  retry = () => {
    this.attempt = 0;
    void this.run();
  };

  /** Save now and wait; resolves `true` when nothing is left unsaved and no save failed. */
  flush = async (): Promise<boolean> => {
    clearTimeout(this.timer);
    this.timer = undefined;
    this.attempt = this.retryDelays.length; // no background retries: the caller decides
    await this.run();
    while (this.running) await this.running;
    return this.snapshot.saveStatus !== "error";
  };

  private schedule() {
    clearTimeout(this.timer);
    this.attempt = 0;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.run();
    }, this.debounceMs);
  }

  private run(): Promise<void> {
    if (this.running) {
      this.rerun = true;
      return this.running;
    }
    this.running = this.cycle().finally(() => {
      this.running = null;
      if (this.rerun) {
        this.rerun = false;
        void this.run();
      }
    });
    return this.running;
  }

  private async cycle() {
    const sent = this.snapshot.state;
    const saved = this.snapshot.saved;
    if (!sent || !saved || this.snapshot.readOnly) return;

    const changed = MEMBER_KEYS.filter((key) => sent[key] !== saved[key] && isSendable(key, sent[key]));
    const profileFields = changed.filter(isProfileField);
    const applicationFields = changed.filter(isApplicationField);
    const rows = sent.beneficiaries
      .map((row, index) => ({ row, index, fields: this.dirtyRowFields(row, saved.beneficiaries[index]) }))
      .filter(({ row, fields }) => fields.length > 0 && !isClearedStoredRow(row));
    if (profileFields.length + applicationFields.length + rows.length === 0) return;

    this.set({ saveStatus: "saving" });
    const failures: Failure[] = [];
    let anySaved = false;
    const note = (result: Failure | null) => {
      if (result) failures.push(result);
      else anySaved = true;
    };

    if (profileFields.length) note(await this.saveMember(sent, profileFields, "profile"));
    if (applicationFields.length) note(await this.saveMember(sent, applicationFields, "application"));
    for (const { row, index, fields } of rows) note(await this.saveRow(row, index, fields));

    if (anySaved) this.invalidateDerived();
    if (failures.some((f) => f.retry) && this.attempt < this.retryDelays.length) {
      const delay = this.retryDelays[this.attempt] ?? 0;
      this.attempt += 1;
      this.timer = setTimeout(() => {
        this.timer = undefined;
        void this.run();
      }, delay);
      return;
    }
    this.set({ saveStatus: failures.length ? "error" : "saved" });
  }

  private dirtyRowFields(row: BeneficiaryRow, before: BeneficiaryRow | undefined): BeneficiaryField[] {
    const base = before ?? emptyRow();
    return ROW_KEYS.filter((key) => row[key] !== base[key] && isSendable(key, row[key]));
  }

  private async saveMember(
    sent: ApplicationFormState,
    fields: MemberField[],
    target: "profile" | "application",
  ): Promise<Failure | null> {
    const send = async (subset: MemberField[]) => {
      if (target === "profile") {
        const profile = await updateProfile(profilePatch(sent, subset));
        this.queryClient.setQueryData<DoctorProfile>(queryKeys.profile, profile);
      } else {
        const app = await updateApplication(this.applicationId, applicationPatch(sent, subset));
        this.queryClient.setQueryData<Application>(queryKeys.applications.detail(this.applicationId), app);
      }
      this.markMemberSaved(sent, subset);
    };
    try {
      await send(fields);
      return null;
    } catch (error) {
      if (retryable(error)) return { retry: true };
      const errors = error instanceof ApiError ? memberFieldErrors(error.fields) : {};
      this.set({ fieldErrors: { ...this.snapshot.fieldErrors, ...errors } });
      const remaining = fields.filter((field) => !errors[field]);
      if (remaining.length > 0 && remaining.length < fields.length) {
        try {
          await send(remaining);
        } catch (second) {
          return { retry: retryable(second) };
        }
      }
      return { retry: false };
    }
  }

  private markMemberSaved(sent: ApplicationFormState, fields: MemberField[]) {
    const saved = this.snapshot.saved;
    if (!saved) return;
    const next = { ...saved };
    for (const field of fields) (next as Record<MemberField, string>)[field] = sent[field];
    this.set({ saved: next });
  }

  private async saveRow(row: BeneficiaryRow, index: number, fields: BeneficiaryField[]): Promise<Failure | null> {
    try {
      let stored: Beneficiary | null = null;
      if (row.id) {
        stored = await updateBeneficiary(this.applicationId, row.id, rowPatch(row, fields));
      } else if (!isEmptyRow(row)) {
        stored = await createBeneficiary(this.applicationId, { row_number: index + 1, ...rowPatch(row, fields) });
      }
      this.markRowSaved(index, row, fields, stored);
      return null;
    } catch (error) {
      if (retryable(error)) return { retry: true };
      const errors = error instanceof ApiError ? rowFieldErrors(error.fields) : {};
      this.set({ rowErrors: { ...this.snapshot.rowErrors, [index]: { ...this.snapshot.rowErrors[index], ...errors } } });
      return { retry: false };
    }
  }

  private markRowSaved(index: number, sentRow: BeneficiaryRow, fields: BeneficiaryField[], stored: Beneficiary | null) {
    const { state, saved } = this.snapshot;
    if (!state || !saved) return;
    const id = stored?.id ?? sentRow.id;
    const savedRow: BeneficiaryRow = { ...(saved.beneficiaries[index] ?? emptyRow()), id };
    for (const field of fields) (savedRow as Record<BeneficiaryField, string>)[field] = sentRow[field];
    const withId = (rows: BeneficiaryRow[], replacement?: BeneficiaryRow) =>
      rows.map((r, i) => (i === index ? (replacement ?? { ...r, id }) : r));
    this.set({
      state: { ...state, beneficiaries: withId(state.beneficiaries) },
      saved: { ...saved, beneficiaries: withId(saved.beneficiaries, savedRow) },
    });
    if (stored) this.upsertCachedBeneficiary(stored);
  }

  // ---- query cache -------------------------------------------------------------------------

  private patchCachedBeneficiary(id: string, update: (b: Beneficiary) => Beneficiary) {
    this.queryClient.setQueryData<Application>(queryKeys.applications.detail(this.applicationId), (old) =>
      old ? { ...old, beneficiaries: old.beneficiaries.map((b) => (b.id === id ? update(b) : b)) } : old,
    );
  }

  private upsertCachedBeneficiary(stored: Beneficiary) {
    this.queryClient.setQueryData<Application>(queryKeys.applications.detail(this.applicationId), (old) => {
      if (!old) return old;
      const exists = old.beneficiaries.some((b) => b.id === stored.id);
      const beneficiaries = exists
        ? old.beneficiaries.map((b) => (b.id === stored.id ? stored : b))
        : [...old.beneficiaries, stored].sort((a, b) => a.rowNumber - b.rowNumber);
      return { ...old, beneficiaries };
    });
  }

  /** The fee quote and validation depend on what was just saved (§10.3). */
  private invalidateDerived() {
    void this.queryClient.invalidateQueries({ queryKey: queryKeys.applications.fees(this.applicationId) });
    void this.queryClient.invalidateQueries({ queryKey: queryKeys.applications.validation(this.applicationId) });
  }
}
