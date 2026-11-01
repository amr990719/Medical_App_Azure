import { useId, useState } from "react";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { parseAmountInput } from "@/features/dues/amount";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { useCreateDuesRequest } from "./queries";

const D = ar.admin.dues;

/**
 * «طلب سداد مستحقات نقابية»: amount (EGP, Arabic digits accepted) and the reason shown to the
 * member. The checks here are UX only; the server's field errors are shown under each field.
 */
export function RequestDuesDialog({
  applicationId,
  reference,
  onClose,
  onDone,
}: {
  applicationId: string;
  reference: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const create = useCreateDuesRequest(applicationId);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [local, setLocal] = useState<{ amount?: string; reason?: string }>({});
  const amountId = useId();
  const reasonId = useId();

  const server = create.error instanceof ApiError ? create.error.fields : {};
  const amountError = local.amount ?? server.amount?.[0];
  const reasonError = local.reason ?? server.reason?.[0];
  const generalError = create.error && !amountError && !reasonError ? create.error.message : null;

  const submit = () => {
    const parsed = parseAmountInput(amount);
    const text = reason.trim();
    const problems = { amount: parsed ? undefined : D.amountInvalid, reason: text ? undefined : D.reasonMissing };
    setLocal(problems);
    if (!parsed || !text) return;
    create.mutate(
      { amount: parsed, reason: text },
      {
        onSuccess: () => {
          onDone(D.requested);
          onClose();
        },
      },
    );
  };

  const field = "w-full rounded-lg border bg-white p-2.5 text-sm focus:border-teal";
  return (
    <Modal
      open
      title={t(D.requestTitle, { reference })}
      onClose={create.isPending ? () => {} : onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            {ar.common.cancel}
          </Button>
          <Button onClick={submit} disabled={create.isPending}>
            {D.send}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={amountId} className="text-sm font-bold text-charcoal">
            {D.amountLabel}
          </label>
          <input
            id={amountId}
            dir="ltr"
            inputMode="decimal"
            autoComplete="off"
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
              setLocal((current) => ({ ...current, amount: undefined }));
            }}
            aria-invalid={amountError ? true : undefined}
            aria-describedby={`${amountId}-hint${amountError ? ` ${amountId}-error` : ""}`}
            className={cx(field, "max-w-48 text-start", amountError ? "border-danger" : "border-border-hover")}
          />
          <p id={`${amountId}-hint`} className="text-xs text-slate">
            {D.amountHint}
          </p>
          {amountError ? (
            <p id={`${amountId}-error`} role="alert" className="text-sm font-semibold text-danger">
              {amountError}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={reasonId} className="text-sm font-bold text-charcoal">
            {D.reasonLabel}
          </label>
          <textarea
            id={reasonId}
            rows={4}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              setLocal((current) => ({ ...current, reason: undefined }));
            }}
            aria-invalid={reasonError ? true : undefined}
            aria-describedby={`${reasonId}-hint${reasonError ? ` ${reasonId}-error` : ""}`}
            className={cx(field, reasonError ? "border-danger" : "border-border-hover")}
          />
          <p id={`${reasonId}-hint`} className="text-xs text-slate">
            {D.reasonHint}
          </p>
          {reasonError ? (
            <p id={`${reasonId}-error`} role="alert" className="text-sm font-semibold text-danger">
              {reasonError}
            </p>
          ) : null}
        </div>
        {generalError ? (
          <p role="alert" className="rounded-lg bg-danger-light p-2.5 text-sm font-semibold text-danger">
            {generalError}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
