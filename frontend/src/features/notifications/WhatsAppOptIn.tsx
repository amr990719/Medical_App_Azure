import { useId } from "react";
import { ApiError } from "@/api/client";
import { ar } from "@/i18n/ar";
import { useSetWhatsAppOptIn, useWhatsAppOptIn } from "./useWhatsAppOptIn";

const W = ar.profile.whatsapp;

/** Consent checkbox for WhatsApp notifications; saves on change, independent of the profile freeze. */
export function WhatsAppOptIn() {
  const preference = useWhatsAppOptIn();
  const save = useSetWhatsAppOptIn();
  const checkboxId = useId();
  const data = preference.data;
  if (!data) return null;
  // Before sign-off nothing is sent, so consent is not asked; a doctor already opted in can still opt out.
  if (!data.whatsappAvailable && !data.whatsappOptIn) return null;

  // A doctor who is already opted in can always opt out, even if the phone later became invalid.
  const blocked = !data.phoneValid && !data.whatsappOptIn;
  const errorMessage = save.error
    ? ((save.error instanceof ApiError ? save.error.fields.whatsapp_opt_in?.[0] : undefined) ?? save.error.message)
    : null;

  return (
    <section aria-labelledby="profile-whatsapp" className="mt-6 rounded-xl border border-border bg-white p-5">
      <h2 id="profile-whatsapp" className="text-lg font-extrabold text-charcoal">
        {W.title}
      </h2>
      <div className="mt-4 flex items-start gap-3">
        <input
          id={checkboxId}
          type="checkbox"
          className="mt-1.5 size-5 shrink-0 accent-teal-deep"
          checked={data.whatsappOptIn}
          disabled={blocked || save.isPending}
          onChange={(event) => save.mutate(event.target.checked)}
        />
        <label htmlFor={checkboxId} className="font-bold text-charcoal">
          {W.consent}{" "}
          {data.phoneNumber ? (
            <bdi dir="ltr" className="font-extrabold">
              {data.phoneNumber}
            </bdi>
          ) : null}
        </label>
      </div>
      {blocked ? <p className="mt-2 text-sm font-semibold text-danger">{W.invalidPhone}</p> : null}
      {errorMessage ? (
        <p role="alert" className="mt-2 font-semibold text-danger">
          {errorMessage}
        </p>
      ) : null}
      <p className="mt-3 text-sm text-slate">{W.hint}</p>
    </section>
  );
}
