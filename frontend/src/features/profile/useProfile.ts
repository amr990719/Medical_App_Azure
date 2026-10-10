import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProfile, updateProfile, type ProfilePatch } from "@/api/endpoints/profile";
import { queryKeys } from "@/api/keys";

export function useProfile() {
  return useQuery({ queryKey: queryKeys.profile, queryFn: fetchProfile });
}

/** PATCH /profile/ (refused with 409 while the fiscal-year application is under review, D49). */
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: ProfilePatch) => updateProfile(changes),
    onSuccess: (profile) => queryClient.setQueryData(queryKeys.profile, profile),
  });
}
