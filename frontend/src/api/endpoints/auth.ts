import { ApiError, apiFetch } from "../client";
import { toCamel } from "../case";
import type { components } from "../schema";
import type { DevUser, Me } from "../types";

type Schemas = components["schemas"];

/** Signed-in user, or null when signed out (401 is an expected answer here). */
export async function fetchMe(): Promise<Me | null> {
  try {
    return toCamel(await apiFetch<Schemas["Me"]>("/auth/me/", { unauthorized: "ignore" }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function logout(): Promise<{ entraLogoutUrl: string | null }> {
  return toCamel(await apiFetch<Schemas["Logout"]>("/auth/logout/", { method: "POST" }));
}

/** Development only: the backend answers 404 unless DEV_AUTH_ENABLED. */
export async function fetchDevUsers(): Promise<DevUser[]> {
  return toCamel(await apiFetch<Schemas["DevUser"][]>("/auth/dev/users/", { unauthorized: "ignore" }));
}

export async function devLogin(email: string): Promise<Me> {
  return toCamel(
    await apiFetch<Schemas["Me"]>("/auth/dev/login/", { method: "POST", body: { email } }),
  );
}

/** Production sign-in is a full-page navigation to the BFF (Entra External ID). */
export function loginUrl(next: string): string {
  return `/api/v1/auth/login/?next=${encodeURIComponent(next)}`;
}
