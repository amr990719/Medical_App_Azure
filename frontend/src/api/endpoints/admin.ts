import { apiFetch } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type {
  AdminApplicationDetail,
  AdminApplicationRow,
  AdminDoctorDetail,
  AdminDoctorRow,
  AdminNote,
  AdminStats,
  ApiAdminApplicationDetail,
  ApiPage,
  ApplicationStatus,
  AuditEntry,
  FeeSchedule,
  NewFeeSchedule,
  Page,
  PaymentStatus,
  TierFees,
} from "../types";

type Schemas = components["schemas"];

/**
 * Admin list filters exactly as the API names them (PROMPT.md §24). The applications page keeps
 * them in the URL, so a filtered list can be bookmarked and the back button restores it.
 */
export type AdminApplicationQuery = {
  search?: string;
  status?: string;
  payment_status?: string;
  fiscal_year?: string;
  governorate?: string;
  syndicate_type?: string;
  sub_syndicate?: string;
  submitted_from?: string;
  submitted_to?: string;
  ordering?: string;
  page?: string;
};

export type AdminDoctorQuery = {
  search?: string;
  syndicate_type?: string;
  governorate?: string;
  page?: string;
};

export async function fetchAdminStats(fiscalYear?: number): Promise<AdminStats> {
  return toCamel(await apiFetch<Schemas["AdminStats"]>("/admin/stats/", { query: { fiscal_year: fiscalYear } }));
}

export async function fetchAdminApplications(query: AdminApplicationQuery): Promise<Page<AdminApplicationRow>> {
  return toCamel(await apiFetch<ApiPage<Schemas["AdminApplicationRow"]>>("/admin/applications/", { query }));
}

/** `reveal` asks for the full national IDs — the server records NATIONAL_ID_REVEALED. */
export async function fetchAdminApplication(id: string, reveal = false): Promise<AdminApplicationDetail> {
  return toCamel(
    await apiFetch<ApiAdminApplicationDetail>(`/admin/applications/${id}/`, {
      query: { reveal_national_id: reveal ? 1 : undefined },
    }),
  );
}

export async function transitionApplication(
  id: string,
  toStatus: ApplicationStatus,
  reviewNotes: string,
): Promise<AdminApplicationDetail> {
  return toCamel(
    await apiFetch<ApiAdminApplicationDetail>(`/admin/applications/${id}/transition/`, {
      method: "POST",
      body: { to_status: toStatus, review_notes: reviewNotes },
    }),
  );
}

/** Confirm or reject the receipt; a non-empty note becomes an internal note (D52). */
export async function reviewPayment(
  id: string,
  paymentStatus: Extract<PaymentStatus, "CONFIRMED" | "REJECTED">,
  note: string,
): Promise<AdminApplicationDetail> {
  return toCamel(
    await apiFetch<ApiAdminApplicationDetail>(`/admin/applications/${id}/payment/`, {
      method: "POST",
      body: { payment_status: paymentStatus, note },
    }),
  );
}

export async function fetchAdminNotes(id: string): Promise<AdminNote[]> {
  return toCamel(await apiFetch<Schemas["AdminNote"][]>(`/admin/applications/${id}/notes/`));
}

export async function addAdminNote(id: string, body: string): Promise<AdminNote> {
  return toCamel(
    await apiFetch<Schemas["AdminNote"]>(`/admin/applications/${id}/notes/`, { method: "POST", body: { body } }),
  );
}

export async function fetchAudit(id: string, page = 1): Promise<Page<AuditEntry>> {
  const result = await apiFetch<ApiPage<Schemas["AuditEntry"]>>(`/admin/applications/${id}/audit/`, {
    query: { page },
  });
  return toCamel(result) as Page<AuditEntry>;
}

export async function fetchAdminDoctors(query: AdminDoctorQuery): Promise<Page<AdminDoctorRow>> {
  return toCamel(await apiFetch<ApiPage<Schemas["AdminDoctorRow"]>>("/admin/doctors/", { query }));
}

export async function fetchAdminDoctor(id: string): Promise<AdminDoctorDetail> {
  return toCamel(await apiFetch<Schemas["AdminDoctorDetail"]>(`/admin/doctors/${id}/`));
}

// Tier and fee keys (`grad_son`) are data, not field names: they are never camelized.
function toFeeSchedule(api: Schemas["FeeSchedule"]): FeeSchedule {
  const { tier_fees, tier_boundaries, ...rest } = api;
  return {
    ...toCamel(rest),
    tierFees: tier_fees as TierFees,
    tierBoundaries: tier_boundaries as [number, number, number],
  };
}

export async function fetchFeeSchedules(): Promise<FeeSchedule[]> {
  const result = await apiFetch<ApiPage<Schemas["FeeSchedule"]>>("/admin/fee-schedules/", {
    query: { page_size: 100 },
  });
  return result.results.map(toFeeSchedule);
}

export async function createFeeSchedule(schedule: NewFeeSchedule): Promise<FeeSchedule> {
  const body: Schemas["FeeScheduleRequest"] = {
    fiscal_year: schedule.fiscalYear,
    tier_fees: schedule.tierFees,
    tier_boundaries: schedule.tierBoundaries,
    admin_fee_member_only: schedule.adminFeeMemberOnly,
    admin_fee_with_beneficiaries: schedule.adminFeeWithBeneficiaries,
    age_cap_threshold: schedule.ageCapThreshold,
    age_cap_amount: schedule.ageCapAmount,
    registration_year_min: schedule.registrationYearMin,
  };
  return toFeeSchedule(
    await apiFetch<Schemas["FeeSchedule"]>("/admin/fee-schedules/", { method: "POST", body }),
  );
}
