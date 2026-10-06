import { Icon } from "@/components/ui/Icon";
import { ar } from "@/i18n/ar";
import type { SaveStatus } from "./types";

/** `جارٍ الحفظ…` / `تم الحفظ` / `تعذّر الحفظ — إعادة المحاولة` (PROMPT.md §9.1). */
export function AutosaveIndicator({ status, onRetry }: { status: SaveStatus; onRetry: () => void }) {
  return (
    <span aria-live="polite" className="inline-flex min-h-8 items-center text-xs font-bold sm:text-sm">
      {status === "saving" ? (
        <span className="inline-flex items-center gap-1.5 text-slate">
          <span className="size-3 animate-spin rounded-full border-2 border-border border-t-teal" aria-hidden />
          {ar.autosave.saving}
        </span>
      ) : status === "saved" ? (
        <span className="inline-flex items-center gap-1 text-teal-deep">
          <Icon name="check" className="size-4" />
          {ar.autosave.saved}
        </span>
      ) : status === "error" ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-danger underline-offset-4 hover:underline"
        >
          <Icon name="alert" className="size-4" />
          {ar.autosave.error}
        </button>
      ) : null}
    </span>
  );
}
