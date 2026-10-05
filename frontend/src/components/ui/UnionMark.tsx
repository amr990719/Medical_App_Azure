import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";

/** The union's text mark: medical cross tile + the two header lines of the paper form. */
export function UnionMark({ inverted = false, className }: { inverted?: boolean; className?: string }) {
  return (
    <span className={cx("flex items-center gap-3", className)}>
      <svg viewBox="0 0 32 32" aria-hidden className="size-9 shrink-0">
        <rect width="32" height="32" rx="7" fill={inverted ? "#F5E642" : "#1A1A2E"} />
        <path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" fill={inverted ? "#1A1A2E" : "#F5E642"} />
      </svg>
      <span className="flex flex-col leading-tight">
        <span className={cx("font-extrabold", inverted ? "text-white" : "text-charcoal")}>
          {ar.app.union}
        </span>
        <span className={cx("text-xs", inverted ? "text-white/70" : "text-slate")}>{ar.app.project}</span>
      </span>
    </span>
  );
}
