import type { ApplicationStatus } from "@/api/types";

/** Statuses an admin can move an application to (PROMPT.md §16.2). */
export type AdminTarget = "UNDER_REVIEW" | "APPROVED" | "NEEDS_CORRECTION" | "REJECTED";

/** Targets for which the transition table requires doctor-visible review notes. */
export const NOTES_REQUIRED = new Set<ApplicationStatus>(["NEEDS_CORRECTION", "REJECTED"]);
