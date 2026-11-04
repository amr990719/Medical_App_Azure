import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWhatsAppOptIn, putWhatsAppOptIn } from "@/api/endpoints/profile";
import { queryKeys } from "@/api/keys";

/** GET /profile/notifications/ — the doctor's own WhatsApp consent and whether the phone allows it. */
export function useWhatsAppOptIn() {
  return useQuery({ queryKey: queryKeys.whatsappOptIn, queryFn: fetchWhatsAppOptIn });
}

/** PUT /profile/notifications/ — refused with 400 on `whatsapp_opt_in` when the phone is unusable. */
export function useSetWhatsAppOptIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (optIn: boolean) => putWhatsAppOptIn(optIn),
    onSuccess: (preference) => queryClient.setQueryData(queryKeys.whatsappOptIn, preference),
  });
}
