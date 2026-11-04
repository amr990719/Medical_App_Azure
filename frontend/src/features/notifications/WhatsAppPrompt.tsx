import { useState } from "react";
import { Link } from "react-router";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { ar } from "@/i18n/ar";
import { useWhatsAppOptIn } from "./useWhatsAppOptIn";

const P = ar.status.whatsappPrompt;

const storageKey = (doctorId: string) => `whatsapp-prompt-dismissed:${doctorId}`;

function wasDismissed(doctorId: string): boolean {
  try {
    return localStorage.getItem(storageKey(doctorId)) !== null;
  } catch {
    return false;
  }
}

function rememberDismissal(doctorId: string): void {
  try {
    localStorage.setItem(storageKey(doctorId), "1");
  } catch {
    // Storage blocked: the prompt is hidden for this render only.
  }
}

/** Nudge on the status page to opt in to WhatsApp. Silent while loading, on error, once opted in, or while WhatsApp is not available. */
export function WhatsAppPrompt() {
  const preference = useWhatsAppOptIn();
  const [hidden, setHidden] = useState(false);
  const data = preference.data;
  if (!data || !data.whatsappAvailable || data.whatsappOptIn || hidden || wasDismissed(data.doctorId)) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-banana-deep bg-banana-light p-4">
      <p className="flex-1 font-bold text-charcoal">{P.message}</p>
      <Link to="/profile" className={buttonClasses("primary", "md")}>
        {P.action}
      </Link>
      <button
        type="button"
        className="font-bold text-slate underline"
        onClick={() => {
          rememberDismissal(data.doctorId);
          setHidden(true);
        }}
      >
        {P.dismiss}
      </button>
    </div>
  );
}
