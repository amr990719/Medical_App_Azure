import { useId, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";

/**
 * Confirmation dialog for a review action with an optional or required text (review notes,
 * internal payment note). The server's answer decides; its Arabic error is shown in place.
 */
export function ActionDialog({
  title,
  body,
  notesLabel,
  notesHint,
  notesRequired = false,
  confirmLabel = ar.admin.actions.confirm,
  confirmVariant = "primary",
  busy,
  error,
  onConfirm,
  onClose,
}: {
  title: string;
  body?: ReactNode;
  notesLabel: string;
  notesHint?: string;
  notesRequired?: boolean;
  confirmLabel?: string;
  confirmVariant?: "primary" | "danger";
  busy: boolean;
  error: string | null;
  onConfirm: (notes: string) => void;
  onClose: () => void;
}) {
  const [notes, setNotes] = useState("");
  const [missing, setMissing] = useState(false);
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  const confirm = () => {
    const text = notes.trim();
    if (notesRequired && !text) {
      setMissing(true);
      return;
    }
    onConfirm(text);
  };

  return (
    <Modal
      open
      title={title}
      onClose={busy ? () => {} : onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {ar.common.cancel}
          </Button>
          <Button variant={confirmVariant} onClick={confirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {body ? <div className="text-charcoal">{body}</div> : null}
        <div className="flex flex-col gap-1.5">
          <label htmlFor={id} className="text-sm font-bold text-charcoal">
            {notesLabel}
          </label>
          <textarea
            id={id}
            rows={4}
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
              setMissing(false);
            }}
            aria-invalid={missing || undefined}
            aria-describedby={cx(notesHint && hintId, (missing || error) && errorId) || undefined}
            className={cx(
              "w-full rounded-lg border bg-white p-2.5 text-sm focus:border-teal",
              missing ? "border-danger" : "border-border-hover",
            )}
          />
          {notesHint ? (
            <p id={hintId} className="text-xs text-slate">
              {notesHint}
            </p>
          ) : null}
        </div>
        {missing || error ? (
          <p id={errorId} role="alert" className="rounded-lg bg-danger-light p-2.5 text-sm font-semibold text-danger">
            {missing ? ar.admin.actions.notesMissing : error}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
