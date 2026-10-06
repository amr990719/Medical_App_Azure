import type { PaymentStatus } from "@/api/types";
import { Icon } from "@/components/ui/Icon";
import { cx } from "@/utils/cx";

// Same visual language as StatusBadge: waiting = banana, done = teal, refused = danger.
const COLOURS: Record<PaymentStatus, string> = {
  NOT_UPLOADED: "bg-smoke text-slate border-border",
  PENDING_REVIEW: "bg-banana-light text-status-submitted-fg border-banana-deep/40",
  CONFIRMED: "bg-teal-light text-teal-deep border-teal/30",
  REJECTED: "bg-danger-light text-status-rejected-fg border-danger/25",
};

/** Payment status pill; the Arabic label comes from reference data (`payment_statuses`). */
export function PaymentBadge({ status, label, className }: { status: PaymentStatus; label: string; className?: string }) {
  return (
    <span
      data-payment-status={status}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-sm font-semibold",
        COLOURS[status],
        className,
      )}
    >
      {status === "CONFIRMED" ? <Icon name="check" className="size-3.5" strokeWidth={2.5} /> : null}
      {label}
    </span>
  );
}
