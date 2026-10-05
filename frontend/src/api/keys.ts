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
};
