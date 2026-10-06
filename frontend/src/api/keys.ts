/** TanStack Query keys, one place so invalidation stays consistent. */
export const queryKeys = {
  me: ["auth", "me"] as const,
  devUsers: ["auth", "dev-users"] as const,
  referenceData: ["reference-data"] as const,
  profile: ["profile"] as const,
  applications: {
    all: ["applications"] as const,
    list: () => ["applications", "list"] as const,
    detail: (id: string) => ["applications", "detail", id] as const,
    fees: (id: string) => ["applications", "detail", id, "fees"] as const,
    validation: (id: string) => ["applications", "detail", id, "validation"] as const,
  },
  admin: {
    all: ["admin"] as const,
    stats: (fiscalYear?: number) => ["admin", "stats", fiscalYear ?? "current"] as const,
    applications: (query: object) => ["admin", "applications", "list", query] as const,
    /** Every cached variant (masked / revealed) of one application, for invalidation. */
    applicationAll: (id: string) => ["admin", "applications", "detail", id] as const,
    application: (id: string, reveal: boolean) =>
      ["admin", "applications", "detail", id, reveal ? "revealed" : "masked"] as const,
    notes: (id: string) => ["admin", "applications", "notes", id] as const,
    audit: (id: string) => ["admin", "applications", "audit", id] as const,
    doctors: (query: object) => ["admin", "doctors", "list", query] as const,
    doctor: (id: string) => ["admin", "doctors", "detail", id] as const,
    feeSchedules: ["admin", "fee-schedules"] as const,
  },
};
