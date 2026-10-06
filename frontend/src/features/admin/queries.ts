import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addAdminNote,
  createFeeSchedule,
  fetchAdminApplication,
  fetchAdminApplications,
  fetchAdminDoctor,
  fetchAdminDoctors,
  fetchAdminNotes,
  fetchAdminStats,
  fetchAudit,
  fetchFeeSchedules,
  reviewPayment,
  transitionApplication,
  type AdminApplicationQuery,
  type AdminDoctorQuery,
} from "@/api/endpoints/admin";
import { queryKeys } from "@/api/keys";
import type { AdminApplicationDetail, ApplicationStatus, NewFeeSchedule } from "@/api/types";

const keys = queryKeys.admin;

export function useAdminStats() {
  return useQuery({ queryKey: keys.stats(), queryFn: () => fetchAdminStats() });
}

/** Server-side filtering, search, ordering and pagination (PROMPT.md §45). */
export function useAdminApplications(query: AdminApplicationQuery) {
  return useQuery({
    queryKey: keys.applications(query),
    queryFn: () => fetchAdminApplications(query),
    placeholderData: keepPreviousData,
  });
}

/** `reveal` = the audited "show full national ID" variant; each variant has its own cache. */
export function useAdminApplication(id: string, reveal = false) {
  return useQuery({
    queryKey: keys.application(id, reveal),
    queryFn: () => fetchAdminApplication(id, reveal),
    placeholderData: keepPreviousData,
  });
}

/**
 * A review action returns the fresh detail (masked): store it, then refresh what it changes —
 * the revealed variant, the audit history, the lists and the dashboard counts.
 */
function useDetailUpdate(id: string) {
  const queryClient = useQueryClient();
  return (detail: AdminApplicationDetail) => {
    queryClient.setQueryData(keys.application(id, false), detail);
    void queryClient.invalidateQueries({ queryKey: keys.application(id, true) });
    void queryClient.invalidateQueries({ queryKey: keys.audit(id) });
    void queryClient.invalidateQueries({ queryKey: ["admin", "applications", "list"] });
    void queryClient.invalidateQueries({ queryKey: ["admin", "stats"] });
  };
}

export function useTransition(id: string) {
  const onDetail = useDetailUpdate(id);
  return useMutation({
    mutationFn: ({ toStatus, reviewNotes }: { toStatus: ApplicationStatus; reviewNotes: string }) =>
      transitionApplication(id, toStatus, reviewNotes),
    onSuccess: onDetail,
  });
}

export function usePaymentReview(id: string) {
  const onDetail = useDetailUpdate(id);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ paymentStatus, note }: { paymentStatus: "CONFIRMED" | "REJECTED"; note: string }) =>
      reviewPayment(id, paymentStatus, note),
    onSuccess: (detail) => {
      onDetail(detail);
      void queryClient.invalidateQueries({ queryKey: keys.notes(id) });
    },
  });
}

export function useAdminNotes(id: string) {
  return useQuery({ queryKey: keys.notes(id), queryFn: () => fetchAdminNotes(id) });
}

export function useAddNote(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => addAdminNote(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.notes(id) });
      void queryClient.invalidateQueries({ queryKey: keys.audit(id) });
    },
  });
}

export function useAudit(id: string, page: number) {
  return useQuery({
    queryKey: [...keys.audit(id), page],
    queryFn: () => fetchAudit(id, page),
  });
}

export function useAdminDoctors(query: AdminDoctorQuery) {
  return useQuery({
    queryKey: keys.doctors(query),
    queryFn: () => fetchAdminDoctors(query),
    placeholderData: keepPreviousData,
  });
}

export function useAdminDoctor(id: string) {
  return useQuery({ queryKey: keys.doctor(id), queryFn: () => fetchAdminDoctor(id) });
}

export function useFeeSchedules() {
  return useQuery({ queryKey: keys.feeSchedules, queryFn: fetchFeeSchedules });
}

export function useCreateFeeSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (schedule: NewFeeSchedule) => createFeeSchedule(schedule),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.feeSchedules }),
  });
}
