import type { ApplicationStatus } from "@/api/types";
import { cx } from "@/utils/cx";
import { Icon } from "./Icon";

// Full class names so Tailwind can see them (§7.3 colours as theme tokens).
const COLOURS: Record<ApplicationStatus, string> = {
  DRAFT: "bg-status-draft-bg text-status-draft-fg border-border",
  SUBMITTED: "bg-status-submitted-bg text-status-submitted-fg border-banana-deep/40",
  UNDER_REVIEW: "bg-status-review-bg text-status-review-fg border-status-review-fg/25",
  NEEDS_CORRECTION: "bg-status-correction-bg text-status-correction-fg border-status-correction-fg/25",
  APPROVED: "bg-status-approved-bg text-status-approved-fg border-status-approved-fg/25",
  REJECTED: "bg-status-rejected-bg text-status-rejected-fg border-status-rejected-fg/25",
};

export interface StatusBadgeProps {
  status: ApplicationStatus;
  /** Arabic label from reference data (`statuses`), never hard-coded here. */
  label: string;
  className?: string;
}

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  return (
    <span
      data-status={status}
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-0.5 text-sm font-bold",
        COLOURS[status],
        className,
      )}
    >
      {status === "UNDER_REVIEW" ? (
        <span data-pulse className="relative flex size-2" aria-hidden>
          <span className="absolute inline-flex size-full rounded-full bg-current opacity-60 motion-safe:animate-ping" />
          <span className="relative inline-flex size-2 rounded-full bg-current" />
        </span>
      ) : null}
      {status === "APPROVED" ? <Icon name="check" className="size-4" strokeWidth={2.5} /> : null}
      {label}
    </span>
  );
}
