import type { DuesReceiptStatus, DuesRequestStatus } from "@/api/types";
import { Icon } from "@/components/ui/Icon";
import { cx } from "@/utils/cx";

// Same visual language as PaymentBadge: waiting = banana, done = teal, refused = danger.
const COLOURS: Record<DuesRequestStatus | DuesReceiptStatus, string> = {
  REQUESTED: "bg-status-correction-bg text-status-correction-fg border-warning/40",
  PENDING_REVIEW: "bg-banana-light text-status-submitted-fg border-banana-deep/40",
  REJECTED: "bg-danger-light text-status-rejected-fg border-danger/25",
  CONFIRMED: "bg-teal-light text-teal-deep border-teal/30",
  CANCELLED: "bg-smoke text-slate border-border",
};

/** Status pill of a dues request or receipt; the Arabic label comes from reference data. */
export function DuesStatusBadge({ status, label }: { status: DuesRequestStatus | DuesReceiptStatus; label: string }) {
  return (
    <span
      data-dues-status={status}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-sm font-semibold",
        COLOURS[status],
      )}
    >
      {status === "CONFIRMED" ? <Icon name="check" className="size-3.5" strokeWidth={2.5} /> : null}
      {label}
    </span>
  );
}
