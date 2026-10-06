import type { AdminApplicationDetail, Beneficiary, DoctorProfile } from "@/api/types";
import type { DraftPreset } from "@/features/application-form/useApplicationDraft";

/**
 * The admin detail in the shape the paper form reads (doctor `Application` + `DoctorProfile`),
 * so the admin print view reuses the same A4 sheet. National IDs stay masked unless the admin
 * used the audited reveal.
 */
export function toDraftPreset(detail: AdminApplicationDetail): DraftPreset {
  const { doctor } = detail;
  const beneficiaries: Beneficiary[] = detail.beneficiaries.map((b) => ({
    id: b.id,
    rowNumber: b.rowNumber,
    kinship: b.kinship,
    fullName: b.fullName,
    birthYear: b.birthYear,
    nationalId: b.nationalId ?? (b.maskedNationalId || null),
    isActive: b.isActive,
    requiredDocuments: b.requiredDocuments,
    documents: b.documents,
    updatedAt: detail.updatedAt,
  }));
  return {
    application: {
      id: detail.id,
      fiscalYear: detail.fiscalYear,
      applicationType: detail.applicationType,
      workStatus: detail.workStatus,
      status: detail.status,
      paymentStatus: detail.paymentStatus,
      referenceNumber: detail.referenceNumber,
      declarationName: detail.declarationName,
      declarationAccepted: detail.declarationAcceptedAt !== null,
      declarationAcceptedAt: detail.declarationAcceptedAt,
      feeSnapshot: detail.feeSnapshot,
      feeSchedule: detail.feeSchedule,
      reviewNotes: detail.reviewNotes,
      reviewedAt: detail.reviewedAt,
      submittedAt: detail.submittedAt,
      createdAt: detail.createdAt,
      updatedAt: detail.updatedAt,
      isEditable: false,
      beneficiaries,
      documents: detail.documents,
    },
    profile: {
      id: doctor.id,
      email: doctor.email,
      fullName: doctor.fullName,
      nationalId: doctor.nationalId ?? (doctor.maskedNationalId || null),
      dateOfBirth: doctor.dateOfBirth,
      birthYear: doctor.birthYear,
      gender: doctor.gender,
      religion: doctor.religion,
      phoneNumber: doctor.phoneNumber,
      syndicateType: doctor.syndicateType,
      subSyndicate: doctor.subSyndicate,
      syndicateRegistrationNumber: doctor.syndicateRegistrationNumber,
      syndicateRegistrationYear: doctor.syndicateRegistrationYear,
      treatmentCardNumber: doctor.treatmentCardNumber,
      // The admin schema types it as a plain string; the value comes from the same enum.
      governorate: doctor.governorate as DoctorProfile["governorate"],
      neighborhood: doctor.neighborhood,
      address: doctor.address,
      updatedAt: detail.updatedAt,
    },
  };
}
