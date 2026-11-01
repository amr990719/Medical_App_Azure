import { Fragment } from "react";
import type { ApplicationStatus, PaymentStatus } from "@/api/types";
import { Button } from "@/components/ui/Button";
import type { ButtonVariant } from "@/components/ui/buttonClasses";
import { ar, t } from "@/i18n/ar";
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
 * appears only once the payment is confirmed and no additional dues are outstanding). The dues
 * request sits right after طلب تصحيح whenever the server allows it (`can_request_dues`). The UI
 * never derives transitions itself.
 */
export function TransitionButtons({
  allowed,
  status,
  paymentStatus,
  onSelect,
  disabled = false,
  canRequestDues = false,
  onRequestDues,
  outstandingDues = 0,
}: {
  allowed: readonly ApplicationStatus[];
  status: ApplicationStatus;
  paymentStatus: PaymentStatus;
  onSelect: (target: AdminTarget) => void;
  disabled?: boolean;
  canRequestDues?: boolean;
  onRequestDues?: () => void;
  /** Dues requests neither confirmed nor cancelled (`outstanding_dues_count`). */
  outstandingDues?: number;
}) {
  const actions = ACTIONS.filter((action) => allowed.includes(action.status));
  const showDues = canRequestDues && onRequestDues !== undefined;
  // Placed after طلب تصحيح, or before رفض الطلب when no correction can be requested.
  const duesAfter = actions.find((a) => a.status === "NEEDS_CORRECTION") ?? actions.find((a) => a.status !== "REJECTED");
  const awaitingDecision = status === "UNDER_REVIEW" && !allowed.includes("APPROVED");
  const duesButton = showDues ? (
    <Button variant="outline" onClick={onRequestDues} disabled={disabled}>
      {ar.admin.actions.requestDues}
    </Button>
  ) : null;

  return (
    <div className="space-y-3">
      {actions.length > 0 || showDues ? (
        <div className="flex flex-wrap gap-2">
          {duesAfter ? null : duesButton}
          {actions.map((action) => (
            <Fragment key={action.status}>
              <Button variant={action.variant} onClick={() => onSelect(action.status)} disabled={disabled}>
                {ar.admin.actions.labels[action.status]}
              </Button>
              {action === duesAfter ? duesButton : null}
            </Fragment>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate">{ar.admin.actions.none}</p>
      )}
      {awaitingDecision && paymentStatus !== "CONFIRMED" ? (
        <p className="rounded-lg bg-banana-light px-3 py-2 text-sm font-semibold text-status-submitted-fg">
          {ar.admin.actions.approveNeedsPayment}
        </p>
      ) : null}
      {awaitingDecision && outstandingDues > 0 ? (
        <p className="rounded-lg bg-banana-light px-3 py-2 text-sm font-semibold text-status-submitted-fg">
          {t(ar.admin.actions.approveNeedsDues, { count: outstandingDues })}
        </p>
      ) : null}
    </div>
  );
}
