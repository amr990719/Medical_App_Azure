import type { ApplicationStatus, PaymentStatus } from "@/api/types";
import { Button } from "@/components/ui/Button";
import type { ButtonVariant } from "@/components/ui/buttonClasses";
import { ar } from "@/i18n/ar";
import type { AdminTarget } from "./transitions";

/** Admin targets in review order, with the look of each action. */
const ACTIONS: { status: AdminTarget; variant: ButtonVariant }[] = [
  { status: "UNDER_REVIEW", variant: "primary" },
  { status: "APPROVED", variant: "primary" },
  { status: "NEEDS_CORRECTION", variant: "outline" },
  { status: "REJECTED", variant: "danger" },
];

/**
 * One button per target the SERVER allows right now (`allowed_transitions`, D53: approval
 * appears only once the payment is confirmed). The UI never derives transitions itself.
 */
export function TransitionButtons({
  allowed,
  status,
  paymentStatus,
  onSelect,
  disabled = false,
}: {
  allowed: readonly ApplicationStatus[];
  status: ApplicationStatus;
  paymentStatus: PaymentStatus;
  onSelect: (target: AdminTarget) => void;
  disabled?: boolean;
}) {
  const actions = ACTIONS.filter((action) => allowed.includes(action.status));
  const approvalWaitsForPayment =
    status === "UNDER_REVIEW" && paymentStatus !== "CONFIRMED" && !allowed.includes("APPROVED");

  return (
    <div className="space-y-3">
      {actions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => (
            <Button key={action.status} variant={action.variant} onClick={() => onSelect(action.status)} disabled={disabled}>
              {ar.admin.actions.labels[action.status]}
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate">{ar.admin.actions.none}</p>
      )}
      {approvalWaitsForPayment ? (
        <p className="rounded-lg bg-banana-light px-3 py-2 text-sm font-semibold text-status-submitted-fg">
          {ar.admin.actions.approveNeedsPayment}
        </p>
      ) : null}
    </div>
  );
}
