import { apiFetch } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type { DoctorProfile, NotificationPreference } from "../types";

export async function fetchProfile(): Promise<DoctorProfile> {
  return toCamel(await apiFetch<components["schemas"]["DoctorProfile"]>("/profile/"));
}

export type ProfilePatch = components["schemas"]["PatchedDoctorProfileRequest"];

export async function updateProfile(changes: ProfilePatch): Promise<DoctorProfile> {
  return toCamel(
    await apiFetch<components["schemas"]["DoctorProfile"]>("/profile/", { method: "PATCH", body: changes }),
  );
}

export async function fetchWhatsAppOptIn(): Promise<NotificationPreference> {
  return toCamel(await apiFetch<components["schemas"]["NotificationPreference"]>("/profile/notifications/"));
}

export async function putWhatsAppOptIn(whatsappOptIn: boolean): Promise<NotificationPreference> {
  return toCamel(
    await apiFetch<components["schemas"]["NotificationPreference"]>("/profile/notifications/", {
      method: "PUT",
      body: { whatsapp_opt_in: whatsappOptIn },
    }),
  );
}
