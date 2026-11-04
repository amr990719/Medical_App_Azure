import { useId, useState } from "react";
import type { NotificationRow, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { formatDateTime } from "@/utils/format";
import { ActionDialog } from "./ActionDialog";
import { choiceLabel } from "./labels";
import { useNotifications, useResendNotification } from "./queries";

const N = ar.admin.notifications;

type Tone = "alert" | "quiet" | "normal";

const KNOWN_ERRORS = new Set(Object.keys(N.errors).filter((code) => code !== "generic"));
const CHANNEL_ERRORS: Record<NotificationRow["channel"], Readonly<Record<string, string>>> = {
  WHATSAPP: N.whatsappErrors,
  EMAIL: N.emailErrors,
};

/** FAILED and EXPIRED stand out; SUPERSEDED (no longer needed) recedes. */
function toneOf(status: NotificationRow["status"]): Tone {
  if (status === "FAILED" || status === "EXPIRED") return "alert";
  if (status === "SUPERSEDED") return "quiet";
  return "normal";
}

const TONE_CLASSES: Record<Tone, string> = {
  alert: "border-danger/40 bg-danger-light",
  quiet: "border-border bg-smoke text-muted",
  normal: "border-border bg-white",
};

/**
 * Only a row that ended FAILED or EXPIRED explains its error code. A row that retried and then
 * succeeded keeps its last code for the record, but is not an error and must not read as one.
 */
function errorLine(row: NotificationRow): string | null {
  if (toneOf(row.status) !== "alert" || !row.errorCode) return null;
  const forChannel = CHANNEL_ERRORS[row.channel][row.errorCode];
  if (forChannel) return forChannel;
  if (KNOWN_ERRORS.has(row.errorCode)) return N.errors[row.errorCode as keyof typeof N.errors];
  return t(N.errors.generic, { code: row.errorCode });
}

/** A SENT row is never shown as delivered: email has no receipt, WhatsApp awaits one. */
function sentLine(row: NotificationRow): string | null {
  if (row.status !== "SENT") return null;
  return row.channel === "EMAIL" ? N.emailAccepted : N.whatsappSent;
}

const canResend = (status: NotificationRow["status"]) =>
  status !== "SUPERSEDED" && status !== "PENDING" && status !== "SENDING";

function NotificationItem({
  row,
  reference,
  onResend,
  busy,
}: {
  row: NotificationRow;
  reference: ReferenceData | undefined;
  onResend: (row: NotificationRow) => void;
  busy: boolean;
}) {
  const tone = toneOf(row.status);
  const error = errorLine(row);
  const sent = sentLine(row);
  return (
    <li
      data-notification-tone={tone}
      className={cx("space-y-1 rounded-lg border p-3 text-sm", TONE_CLASSES[tone])}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-semibold", tone === "quiet" ? "text-muted" : "text-charcoal")}>
          {choiceLabel(reference?.notificationEvents, row.event)}
        </span>
        <span className="text-slate">{choiceLabel(reference?.notificationChannels, row.channel)}</span>
        <span
          className={cx(
            "rounded-full border px-2.5 py-0.5 font-semibold",
            tone === "alert" ? "border-danger/25 bg-white font-extrabold text-status-rejected-fg" : "border-border bg-white",
          )}
        >
          {choiceLabel(reference?.notificationStatuses, row.status)}
        </span>
        {canResend(row.status) ? (
          <Button
            variant="ghost"
            className="ms-auto border border-border bg-white"
            onClick={() => onResend(row)}
            disabled={busy}
          >
            {N.resend}
          </Button>
        ) : null}
      </div>
      <p className="text-xs text-muted">
        <span dir="ltr">{row.recipientMasked}</span> · {formatDateTime(row.createdAt)}
        {row.attempts > 1 ? ` · ${t(N.attempts, { n: row.attempts })}` : null}
      </p>
      {sent ? <p className="text-slate">{sent}</p> : null}
      {error ? <p className="font-semibold text-status-rejected-fg">{error}</p> : null}
    </li>
  );
}

/**
 * «الإشعارات»: every message sent to the member about this application, newest first, with the
 * server's status as is. Resend asks for confirmation; the server's 409 message is shown in the
 * dialog and the list stays.
 */
export function NotificationsPanel({
  applicationId,
  reference,
}: {
  applicationId: string;
  reference: ReferenceData | undefined;
}) {
  const titleId = useId();
  const list = useNotifications(applicationId);
  const resend = useResendNotification(applicationId);
  const [pending, setPending] = useState<NotificationRow | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const close = () => {
    setPending(null);
    resend.reset();
  };
  const confirm = () => {
    if (!pending) return;
    resend.mutate(pending.id, {
      onSuccess: () => {
        close();
        setFlash(N.resent);
      },
    });
  };

  return (
    <section aria-labelledby={titleId} className="space-y-3 rounded-xl border border-border bg-white p-5">
      <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
        {N.title}
      </h2>
      {flash ? (
        <p role="status" className="text-sm font-semibold text-teal-deep">
          {flash}
        </p>
      ) : null}
      {list.isError ? (
        <p role="alert" className="text-sm text-status-rejected-fg">
          {N.loadError}
        </p>
      ) : list.isPending ? (
        <p className="text-sm text-slate">{N.loading}</p>
      ) : list.data.length === 0 ? (
        <p className="text-sm text-slate">{N.empty}</p>
      ) : (
        <ul className="space-y-2">
          {list.data.map((row) => (
            <NotificationItem
              key={row.id}
              row={row}
              reference={reference}
              onResend={(target) => {
                setFlash(null);
                setPending(target);
              }}
              busy={resend.isPending}
            />
          ))}
        </ul>
      )}

      {pending ? (
        <ActionDialog
          title={N.resendTitle}
          body={N.resendConfirm}
          confirmLabel={N.resend}
          busy={resend.isPending}
          error={resend.error?.message ?? null}
          onClose={close}
          onConfirm={confirm}
        />
      ) : null}
    </section>
  );
}
