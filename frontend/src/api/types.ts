/**
 * SPA-facing (camelCase) types. Generated types come from `schema.d.ts`
 * (`npm run gen:api` from backend/openapi.yaml); the few endpoints the schema types as a plain
 * object (reference data, fee quote, validation) are described by hand below, matching
 * backend/apps/reference/api/views.py, fees/services.py and applications/validation.py.
 *
 * Hand-written API shapes are `type` aliases, not interfaces, so `Camelize` can map them.
 */
import type { Camelize } from "./case";
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Role = Schemas["RoleEnum"];
export type ApplicationStatus = Schemas["ApplicationStatusEnum"];
export type PaymentStatus = Schemas["PaymentStatusEnum"];
export type DocumentType = Schemas["DocumentTypeEnum"];
export type Kinship = Schemas["KinshipEnum"];
export type ApplicationType = Schemas["ApplicationTypeEnum"];

export type CurrentUser = Camelize<Schemas["CurrentUser"]>;
export type Me = Camelize<Schemas["Me"]>;
export type DevUser = Camelize<Schemas["DevUser"]>;
export type DoctorProfile = Camelize<Schemas["DoctorProfile"]>;
export type DocumentSummary = Camelize<Schemas["DocumentSummary"]>;
export type Application = Camelize<Schemas["Application"]>;
export type Beneficiary = Camelize<Schemas["Beneficiary"]>;

export type ApiPage<T> = { count: number; next?: string | null; previous?: string | null; results: T[] };
export type Page<T> = Camelize<ApiPage<T>>;

// ---- Reference data (GET /reference-data/) ------------------------------------------------

export type Choice<V extends string = string> = { value: V; label: string };

export type ApiDocumentRequirement = {
  type: DocumentType;
  required: boolean;
  label: string;
  ocr_capable: boolean;
  stage?: "form" | "submit";
  /** Photos: supported image formats only, even when PDF documents are enabled. */
  images_only?: boolean;
  /** Arabic guidance shown next to the upload (e.g. the white-background photo rule). */
  hints?: string[];
};

export type ApiReferenceData = {
  fiscal_year: number;
  max_beneficiaries: number;
  governorates: string[];
  syndicate_types: Choice<Schemas["SyndicateTypeEnum"]>[];
  work_statuses: Choice<Schemas["WorkStatusEnum"]>[];
  religions: Choice<Schemas["ReligionEnum"]>[];
  genders: Choice<Schemas["GenderEnum"]>[];
  /** `selectable: false` = retired (DAUGHTER): never offered, still labels and prices stored rows. */
  kinships: (Choice<Kinship> & { fee_key: string; selectable: boolean })[];
  application_types: Choice<ApplicationType>[];
  statuses: Choice<ApplicationStatus>[];
  payment_statuses: Choice<PaymentStatus>[];
  document_rules: {
    document_types: { type: DocumentType; label: string; ocr_capable: boolean; images_only: boolean }[];
    /** Global member slots; the application's own list is `member_required_documents`. */
    member: ApiDocumentRequirement[];
    /** Member slots whose requirement depends on this application (evaluated by the server). */
    member_conditional: Partial<
      Record<DocumentType, { required_with_kinship?: Kinship; required_with_application_type?: ApplicationType }>
    >;
    child_national_id_age: number;
    photo_exempt_child_age: number;
    kinships: Record<Kinship, { base_rule: string; extra_required: DocumentType[] }>;
    base_rules: Record<string, unknown>;
  };
  ocr_enabled: boolean;
  features: { allow_pdf: boolean; allow_heic: boolean };
  upload: {
    max_bytes: number;
    receipt_min_width: number;
    receipt_min_height: number;
    accepted_content_types: string[];
    /** Accepted for image-only slots (personal photos). */
    image_content_types: string[];
  };
};

export type ReferenceData = Camelize<ApiReferenceData>;
export type DocumentRequirement = Camelize<ApiDocumentRequirement>;

// ---- Fee quote (GET /applications/{id}/fees/) ---------------------------------------------

export type ApiFeeQuote = {
  fiscal_year: number;
  tier: number | null;
  breakdown: { label: string; fee: number; note: string }[];
  admin_fee: number;
  total: number;
  is_valid: boolean;
  error_message: string;
  schedule_id: string | null;
};

export type FeeQuote = Camelize<ApiFeeQuote>;

// ---- Validation (GET /applications/{id}/validation/) --------------------------------------

export type ApiValidationIssue = { step: number; field: string; code: string; message: string };

export type ApiValidationResult = {
  is_valid: boolean;
  errors: ApiValidationIssue[];
  by_step: Record<string, ApiValidationIssue[]>;
  steps_complete: Record<string, boolean>;
  warnings: ApiValidationIssue[];
  submit_ready: boolean;
};

export type ValidationResult = Camelize<ApiValidationResult>;

// ---- Admin (GET /admin/...) -----------------------------------------------------------------

export type AuditAction = Schemas["ActionEnum"];
export type AdminStats = Camelize<Schemas["AdminStats"]>;
export type AdminApplicationRow = Camelize<Schemas["AdminApplicationRow"]>;
export type AdminDoctorRow = Camelize<Schemas["AdminDoctorRow"]>;
export type AdminDoctorDetail = Camelize<Schemas["AdminDoctorDetail"]>;
export type AdminNote = Camelize<Schemas["AdminNote"]>;
export type AuditEntry = Camelize<Omit<Schemas["AuditEntry"], "metadata"> & { metadata: Record<string, unknown> }>;

type ApiAdminBeneficiary = Omit<Schemas["AdminBeneficiary"], "required_documents"> & {
  required_documents: ApiDocumentRequirement[];
};

/** `fee_snapshot` is the fee quote stored at submission (null before the first submission). */
export type ApiAdminApplicationDetail = Omit<
  Schemas["AdminApplicationDetail"],
  "fee_snapshot" | "beneficiaries" | "allowed_transitions" | "reviewed_by_email" | "member_required_documents"
> & {
  fee_snapshot: ApiFeeQuote | null;
  beneficiaries: ApiAdminBeneficiary[];
  allowed_transitions: ApplicationStatus[];
  reviewed_by_email: string | null;
  member_required_documents: ApiDocumentRequirement[];
};

export type AdminApplicationDetail = Camelize<ApiAdminApplicationDetail>;
export type AdminBeneficiary = AdminApplicationDetail["beneficiaries"][number];

export type FeeKey = "member" | "spouse" | "child" | "grad_son" | "parent";
export type TierKey = "0" | "1" | "2" | "3" | "4";
/** `null` = not eligible at that tier (only tier 0 `grad_son`), never free. */
export type TierRow = Record<FeeKey, number | null>;
/** Every schedule defines tiers 0-4. */
export type TierFees = Record<TierKey, TierRow>;

/** Tier keys ("0".."4") and fee keys stay as data; only the outer fields are camelized. */
export type FeeSchedule = Camelize<Omit<Schemas["FeeSchedule"], "tier_fees" | "tier_boundaries">> & {
  tierFees: TierFees;
  tierBoundaries: [number, number, number];
};

export type NewFeeSchedule = {
  fiscalYear: number;
  tierFees: TierFees;
  tierBoundaries: [number, number, number];
  adminFeeBase: number;
  adminFeePerBeneficiary: number;
  ageCapThreshold: number;
  ageCapAmount: number;
  registrationYearMin: number;
};
