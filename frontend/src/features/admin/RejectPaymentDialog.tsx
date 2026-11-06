import { useId, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";

const T = ar.admin.payment;

/**
 * Reject the payment receipt (D220): a required reason the member sees (it becomes the correction
 * note and the application returns to the member) and an optional internal note (D52). The
 * server checks the reason again; its Arabic error is shown in place.
 */
export function RejectPaymentDialog({
  busy,
  error,
  onConfirm,
  onClose,
}: {
  busy: boolean;
  error: string | null;
  onConfirm: (input: { reason: string; note: string }) => void;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [missing, setMissing] = useState(false);
  const id = useId();
  const reasonId = `${id}-reason`;
  const noteId = `${id}-note`;
  const errorId = `${id}-error`;

  const confirm = () => {
    const text = reason.trim();
    if (!text) {
      setMissing(true);
      return;
    }
    onConfirm({ reason: text, note: note.trim() });
  };

  const field = "w-full rounded-lg border bg-white p-2.5 text-sm focus:border-teal";

  return (
    <Modal
      open
      title={T.rejectTitle}
      onClose={busy ? () => {} : onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {ar.common.cancel}
          </Button>
          <Button variant="danger" onClick={confirm} disabled={busy}>
            {ar.admin.actions.confirm}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-charcoal">{T.rejectBody}</p>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={reasonId} className="text-sm font-bold text-charcoal">
            {T.reasonLabel}
            <span aria-hidden="true" className="ms-0.5 text-danger">
              *
            </span>
          </label>
          <textarea
            id={reasonId}
            rows={3}
            required
            aria-required="true"
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              setMissing(false);
            }}
            aria-invalid={missing || undefined}
            aria-describedby={missing || error ? errorId : undefined}
            className={cx(field, missing ? "border-danger" : "border-border-hover")}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={noteId} className="text-sm font-bold text-charcoal">
            {T.noteLabel}
          </label>
          <textarea
            id={noteId}
            rows={3}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className={cx(field, "border-border-hover")}
          />
        </div>
        {missing || error ? (
          <p id={errorId} role="alert" className="rounded-lg bg-danger-light p-2.5 text-sm font-semibold text-danger">
            {missing ? T.reasonMissing : error}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
