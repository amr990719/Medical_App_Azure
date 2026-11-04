# Design: doctor notifications (WhatsApp first, email fallback)

**Date:** 2026-11-02 (revised the same day after the third-party audit; see section 13)
**Status:** awaiting owner review of this document. Amended 2026-11-04: email is the main channel and WhatsApp is parked behind `WHATSAPP_ENABLED` (section 14).
**Providers (owner decision):** Meta WhatsApp Cloud API and Amazon SES (not Azure Communication Services)

## 1. Goal

When an admin or the system changes something a doctor must act on or wants to know, the doctor is
told on WhatsApp. If WhatsApp cannot reach them, or they have not opted in, they are told by email
at their registered address.

**Success means:**
- A status change and its notification commit together, or neither does.
- An outage at Meta or AWS never blocks or rolls back an admin action.
- A WhatsApp failure reported minutes later still produces the email.
- A message asking the doctor to act is not sent once that action is no longer needed.
- A doctor can stop WhatsApp messages by replying with a stop word.
- An admin can see on the application page what each provider reported, and resend.
- No message text, full phone number or full email address is stored on notification rows or logged.
  The profile and submission snapshot keep contact data as they do today, and Meta and AWS receive
  what they need to deliver.

**What this does not promise:** delivery is at least once, so a doctor can occasionally receive the
same news twice. Accepted email means the provider took it, not that the doctor received or read it.

**Out of scope for this version:** free-text messages from admins, conversations with doctors on
WhatsApp (only the stop and help replies in section 7 are handled), SES bounce tracking per
notification, phone verification codes, SMS, scheduled reminders, automatic purge of old rows
(section 11).

PROMPT.md does not cover notifications, so this document is the requirement. Its decisions are
recorded in `docs/progress.md` when the work lands.

## 2. Events

`NotificationEvent` lives in `apps/reference/constants.py` with the other enums. Each hook calls
`notifications.services.enqueue()` inside the transaction that already wraps the change.

| # | Event | Hook | Condition |
|---|---|---|---|
| 1 | `APPLICATION_RECEIVED` | `applications.services.transition` | target `SUBMITTED` (first submission and resubmission) |
| 2 | `CORRECTION_NEEDED` | `applications.services.transition` | target `NEEDS_CORRECTION` |
| 3 | `APPROVED` | `applications.services.transition` | target `APPROVED` |
| 4 | `REJECTED` | `applications.services.transition` | target `REJECTED` |
| 5 | `PAYMENT_CONFIRMED` | `applications.services.set_payment_status` | status actually changed to `CONFIRMED` |
| 6 | `PAYMENT_RECEIPT_REJECTED` | `applications.services.set_payment_status` | status actually changed to `REJECTED` |
| 7 | `DUES_REQUESTED` | `dues.services.create_dues_request` | always |
| 8 | `DUES_CONFIRMED` | `dues.services.review_dues_receipt` | decision `CONFIRMED` |
| 9 | `DUES_RECEIPT_REJECTED` | `dues.services.review_dues_receipt` | decision `REJECTED` |
| 10 | `DUES_CANCELLED` | `dues.services.cancel_dues_request` | always |

`SUBMITTED → UNDER_REVIEW` sends nothing.

For events 5 and 6 the hook sits inside the existing `if app.payment_status != status` branch, so
re-sending the same status sends nothing.

### Still relevant?

`notifications.services.still_relevant(row)` runs when a row is claimed, so it covers every attempt,
every fallback email and every resend, and rows waiting out a pause in `off` mode. A row that fails
it becomes `SUPERSEDED` and sends nothing, with no fallback.

| # | Event | Sent only while |
|---|---|---|
| 2 | `CORRECTION_NEEDED` | application status is `NEEDS_CORRECTION` |
| 5 | `PAYMENT_CONFIRMED` | `payment_status` is `CONFIRMED` |
| 6 | `PAYMENT_RECEIPT_REJECTED` | `payment_status` is `REJECTED` |
| 7 | `DUES_REQUESTED` | the dues request is `REQUESTED` and the application is `SUBMITTED`, `UNDER_REVIEW` or `NEEDS_CORRECTION` (dues requests freeze on a final application, so a rejected or approved one has nothing left to pay) |
| 9 | `DUES_RECEIPT_REJECTED` | the dues request is `REJECTED` and the application is `SUBMITTED`, `UNDER_REVIEW` or `NEEDS_CORRECTION` |

The other events state something that stays true (`APPROVED` and `REJECTED` are final in
`applications/transitions.py`; `CONFIRMED` and `CANCELLED` are final for a dues request), so they
are always relevant.

## 3. Data model

New app: `apps/notifications`. All PKs are UUIDs and foreign keys use `PROTECT`, as elsewhere.

### `Notification` (one row per channel attempt chain)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `application` | FK `InsuranceApplication` | required |
| `dues_request` | FK `SyndicateDuesRequest`, nullable | events 7–10; supplies the amount at send time |
| `event` | choices | section 2 |
| `channel` | choices | `WHATSAPP`, `EMAIL` |
| `status` | choices | section 4 |
| `provider_message_id` | char, nullable | SES `MessageId`; for WhatsApp the SHA-256 hex digest of Meta's `wamid` (see the note below) |
| `attempts` | small int | default 0; also identifies the current claim (section 4) |
| `next_attempt_at` | datetime | when the row becomes due |
| `sending_started_at` | datetime, nullable | set only while `SENDING`; detects interrupted sends |
| `expires_at` | datetime | set once at enqueue; a fallback copies it (section 5) |
| `error_code` | char, blank | provider code or an internal code; never provider free text |
| `recipient_masked` | char, blank | filled at send: `010•••••678` or `a•••@example.com` |
| `fallback_of` | one-to-one self FK, nullable | the WhatsApp row this email replaces |
| `created_by` | FK user, nullable | the admin for a resend; null for automatic rows |
| `created_at`, `sent_at`, `delivered_at`, `updated_at` | datetime | |

**Constraints and indexes:**
- `CHECK` on `event`, `channel` and `status` values.
- `CHECK`: `dues_request` is set exactly when the event is 7–10.
- `CHECK`: a row with `fallback_of` is `EMAIL`.
- **WhatsApp IDs are stored hashed.** Meta's `wamid` is believed to decode to contain the recipient's number (NOT VERIFIED on real traffic), which would put a full phone number on the row. `formatting.hash_provider_id` (SHA-256, 64 hex characters, fits the column) is applied by `record_accepted` and by the webhook before its lookup. Email keeps the SES `MessageId`.
- Unique `(channel, provider_message_id)` where the ID is not null. The webhook finds a row by it,
  filtered to `WHATSAPP`.
- `fallback_of` is one-to-one, as a second line of defence behind the shared service in section 4.
- Partial index on `(next_attempt_at)` where status is `PENDING`.
- Partial index on `(sent_at)` where channel is `WHATSAPP` and status is `SENT`.
- Index on `(application, created_at)`.

The service also checks what the database cannot: a dues row's request belongs to its application,
and a fallback has the same application, event and dues request as its parent.

**No uniqueness on event and application.** A second correction request on the same application
must send again. `enqueue()` runs once per change and retries reuse the same row, which limits
duplicates but cannot remove them (section 5).

### `Doctor` additions

- `whatsapp_opt_in` boolean, `db_default=False`.
- `whatsapp_opt_in_at` datetime, nullable.
- `whatsapp_help_sent_at` datetime, nullable: limits the help reply in section 7.

Existing doctors are not opted in, so they receive email until they opt in.

### Audit

New `AuditAction` values: `WHATSAPP_OPT_IN_CHANGED`, `NOTIFICATION_RESENT`. Metadata holds IDs and
booleans plus the source of a consent change (`profile` or `whatsapp_reply`), never a phone number or
address. A stop reply is recorded with `actor=None`, which `audit.services.record` already treats as
a system action. Automatic sends are not audited; the `Notification` row is their record.

## 4. Status lifecycle

Every change goes through one service, `notifications.services.apply_transition()`. In one
transaction it locks and re-reads the row, rejects any change not listed below, applies the change
and creates the fallback email if the row needs one. A crash therefore cannot leave a `FAILED`
WhatsApp row that should have an email but does not, and a stale read cannot turn `DELIVERED` into
`FAILED`.

| From | Trigger | To | Field changes |
|---|---|---|---|
| `PENDING` | past `expires_at` | `EXPIRED` | no attempt used |
| `PENDING` | `still_relevant` is false | `SUPERSEDED` | no attempt used |
| `PENDING` | WhatsApp only: `WHATSAPP_ENABLED` is off (section 14) | `FAILED` | no attempt used; `WHATSAPP_DISABLED`; email row |
| `PENDING` | `allowlist` mode, recipient not listed | `SUPPRESSED` | no attempt used; no fallback |
| `PENDING` | WhatsApp only: opt-in withdrawn or phone invalid | `FAILED` | no attempt used; `OPTED_OUT`; email row |
| `PENDING` | claimed | `SENDING` | `attempts` +1; `sending_started_at` set |
| `SENDING` | provider accepted | `SENT` | `provider_message_id`, `sent_at`, `recipient_masked` set; `sending_started_at` cleared |
| `SENDING` | not accepted, temporary, attempts left | `PENDING` | `error_code`, `next_attempt_at` set; `sending_started_at` cleared |
| `SENDING` | anything else that ends the row (section 5) | `FAILED` | `error_code` set; `sending_started_at` cleared; email row if WhatsApp |
| `SENT` | WhatsApp receipt `delivered` or `read` | `DELIVERED` | `delivered_at` set |
| `SENT` | WhatsApp receipt `failed`, or delivery timeout | `FAILED` | `error_code` set; email row |
| `FAILED` | late WhatsApp `delivered` or `read` | `DELIVERED` | `delivered_at` set; an email already created still sends |

The checks at claim run in the order listed, inside the claim transaction. The `WHATSAPP_DISABLED`
check runs right after the relevance check and before the allowlist check, so a parked WhatsApp row
never reaches a client and its fallback email passes its own checks. `SENT` is final for
email.

**Recording a send result:** the result applies only if the row is still `SENDING` with the
`attempts` value this sender claimed. Otherwise recovery has already decided the row, and the result
is dropped and logged by notification ID.

**Locks:** callers take locks in the order application, dues request, notification. Notification
code never takes an application or dues lock while holding a notification lock, and the claim reads
the source rows without locking them.

## 5. Routing and fallback

`enqueue()` picks the first channel: `WHATSAPP` if the doctor has opted in and the phone is a valid
mobile, otherwise `EMAIL`. It sets `expires_at` to now plus `NOTIFICATION_MAX_AGE_HOURS`.

A WhatsApp row ends as `FAILED` and gets a linked email row (`fallback_of`) in each of these cases:

| Trigger | `error_code` |
|---|---|
| Opt-in withdrawn or phone invalid at claim | `OPTED_OUT` |
| `WHATSAPP_ENABLED` is off at claim (section 14) | `WHATSAPP_DISABLED` |
| Meta returns a permanent error (4xx other than 429) | Meta's code |
| Meta did not accept the message after 3 attempts (connection refused, connect timeout, 5xx, 429) | Meta's code or `CONNECT_FAILED` |
| The request was sent but the result is unknown (read timeout, connection dropped) | `UNKNOWN_RESULT` |
| Webhook reports `failed` | Meta's code, e.g. `131026` |
| Still `SENT` with no `delivered` after `WHATSAPP_DELIVERY_TIMEOUT_MINUTES` (default 30) | `NO_DELIVERY_RECEIPT` |
| Row stuck in `SENDING` longer than 10 minutes (sender crashed) | `SEND_INTERRUPTED` |

**Why an unknown result or crashed send goes to email, not back to WhatsApp:** the first attempt may
have reached the doctor. At worst they get the same news on both channels, which is harmless, while
a second WhatsApp retry could repeat indefinitely.

**Why any permanent 4xx goes to email:** the exact mapping of Meta's error codes is `NOT VERIFIED`.
A wrong classification costs one email. An expired token or a paused template takes the same path,
so doctors are still told and the `FAILED` warnings raise the alert.

**Retry timing:** the second attempt is due 5 minutes after the first and the third 15 minutes after
the second. Email retries temporary errors and unknown results the same way, because it is the last
channel and a duplicate email is better than none. An email row that runs out of attempts, gets a
permanent error or is stuck in `SENDING` ends as `FAILED` with no further fallback, and the admin
panel shows it.

**Maximum age belongs to the event.** A fallback copies its parent's `expires_at`, so it cannot
extend the news's life, and a fallback created after that time becomes `EXPIRED` on the next run. A
resend is a deliberate admin decision: it passes the relevance check, is audited, and gets a new
`expires_at`.

**Known and accepted:**
- A doctor whose phone is off for over 30 minutes may receive both messages.
- A message accepted just before its source changes can arrive beside the change's own message, for
  example a dues request and its cancellation.
- A webhook arriving before the sender commits `SENT` finds no row and is ignored. The delivery
  timeout covers it: at worst an extra email, or the fallback arrives up to 30 minutes later.
- A fallback email that bounces gives the admin no signal on the application page.

## 6. Sender

`manage.py send_notifications` runs as a scheduled Container Apps job named `notify`, modelled on
`cleanupJob` in `infrastructure/modules/container-app.bicep`, with a new `notify` mode in
`backend/entrypoint.sh`.

- **Schedule:** `notifyCron` parameter, default `*/5 * * * *`. `replicaTimeout` is 280 seconds, which
  makes overlap unlikely but does not prevent it. Correctness relies on the database, not the
  schedule. A forced stop at the timeout ends in the `SEND_INTERRUPTED` path.
- **Each run, in order:**
  1. Mark overdue `PENDING` rows `EXPIRED`.
  2. Recover rows stuck in `SENDING`.
  3. Apply the delivery timeout to `SENT` WhatsApp rows.
  4. Send due rows, email first and then WhatsApp, oldest first within each, up to 200 per run or a
     240-second budget. Stop claiming with under 15 seconds left.
  5. Log the run summary.

  Steps 1–3 each handle at most 500 rows per run.
- **Provider outage:** after 5 consecutive errors from one provider, the run skips that provider's
  remaining rows. They use no attempt and wait for the next run, so a Meta outage cannot use up the
  budget that fallback emails need. Temporary errors, unknown results and unexpected send errors
  count. On email only, permanent errors count too, because it is the last channel, except
  `BadRequestException`, which is one recipient's problem. A success resets the count, and so does a
  permanent WhatsApp error, because the provider answered and the row still reaches email.
- **Claiming a row:** a short transaction uses `select_for_update(skip_locked=True)`, applies the
  checks in section 4, sets `SENDING` and commits. The provider call happens **outside** any
  transaction. A second transaction records the outcome through `apply_transition()`.
- **No immediate send after commit.** The job is the only path for event notifications, so admin
  requests never wait on a provider. Five minutes is the normal polling delay, not a guarantee.
- **`NOTIFICATIONS_MODE`:**
  - `off` (default): only steps 1 and 5 run. Rows still accumulate and expire.
  - `allowlist`: sends only to `NOTIFICATIONS_ALLOWLIST`, for WhatsApp, direct email and fallback
    alike; others become `SUPPRESSED`. Dev uses this.
  - `live`: sends to everyone. Production settings refuse `live` if a required provider setting is
    missing or `NOTIFICATION_PROVIDERS` selects the fakes.

  The job and the web app both read this setting, because the web app sends the replies in section 7.
  Both must be changed together.

### Logging and alerts

- **Allowlisted fields only:** notification logs carry notification ID, event, channel, status,
  error code and counts. `FAILED` and `EXPIRED` log at `WARNING`. The run summary (`notify_run`) logs
  counts and the age in seconds of the oldest due row.
- **Provider errors are translated before anything logs them.** Clients raise the exceptions below
  with a code only, using `raise … from None`, so request bodies and provider text cannot reach a
  traceback. SDK wire logging stays off.
- **Telemetry must start before Django.** `TelemetryLogHandler` binds its provider when Django builds
  the logging handlers, and today only `config/wsgi.py` calls `configure_telemetry()`. `manage.py`
  therefore calls it before `execute_from_command_line` when the command is `send_notifications`. A
  call inside `handle()` would be too late. The command flushes the logger provider before exiting.

**Alerts** (Application Insights; the job and alerts need proving end to end in phase 3):
- any `FAILED` or `EXPIRED` warning;
- oldest due row older than 30 minutes, from `notify_run`;
- no `notify_run` for 15 minutes, which catches a job that stops running;
- `notify` job execution failures.

### Provider clients

`notifications/providers.py` defines `WhatsAppClient.send_template()`, `WhatsAppClient.send_text()`
(section 7 replies only) and `EmailClient.send()`. They return a provider message ID or raise
`TemporaryProviderError`, `UnknownResultError` or `PermanentProviderError`. Tests and local
development use fakes selected by `NOTIFICATION_PROVIDERS`.

- **WhatsApp:** `requests` (already a dependency) against the Graph API, with the version pinned in a
  setting and `timeout=(3, 7)` for connect and read. A connect failure raises
  `TemporaryProviderError`; a read timeout raises `UnknownResultError`.
- **Email:** `boto3` (new dependency) with the SES v2 API, in the selected Region, HTML plus plain
  text, UTF-8. `Config(connect_timeout=3, read_timeout=7, retries={"total_max_attempts": 1})`, so
  each attempt in the database is one HTTP request. Fetching credentials must be bounded the same
  way; the spike in section 12 records how.

## 7. WhatsApp webhook

`/api/v1/notifications/whatsapp/webhook/`, with empty `authentication_classes` and
`permission_classes` (the defaults would reject Meta) and no CSRF.

- **`GET`:** Meta's subscription handshake. It checks `hub.mode` is `subscribe` and `hub.verify_token`
  matches, then returns `hub.challenge`.
- **`POST`:**
  1. Read the raw bytes before any parser. Verify `X-Hub-Signature-256` as HMAC-SHA256 of the **raw
     body** with the app secret, using a constant-time comparison. Failure returns 403 and nothing is
     parsed.
  2. Ignore entries whose `metadata.phone_number_id` is not ours.
  3. For each entry in `statuses`, find the row by `provider_message_id` and apply the table below
     through `apply_transition()`. Unknown IDs are ignored (section 5).
  4. For each entry in `messages`, apply the stop and help rules below. Ignore everything else.
  5. Return 200 only after the database work commits. A database failure returns 500 so Meta retries.

| Webhook status | Row in `SENT` | Row in `DELIVERED` | Row in `FAILED` |
|---|---|---|---|
| `sent` | no change | no change | no change |
| `delivered`, `read` | → `DELIVERED` | no change | → `DELIVERED`; an email already created still sends |
| `failed` | → `FAILED` + email row | no change | no change |

Meta retries for up to 7 days and events can arrive out of order, so every branch must be safe to
repeat. The endpoint returns no data. Django's request-size limit bounds the body; phase 0 checks it
against Meta's documented maximum.

**Payloads and message text must never be logged or stored**, because they contain phone numbers and
personal content.

### Stop and help replies

WhatsApp's Business Policy requires honouring requests to stop, so these are the only inbound
messages handled.

- **Finding the doctor:** convert the sender from `2010…` to the stored `010…` form and match every
  `Doctor` with that number. `phone_number` is not unique, so all matches are treated alike. A number
  that matches no doctor gets no action and no reply.
- **Stop:** the whole text, after trimming spaces and punctuation and ignoring case, is `إيقاف`,
  `ايقاف` or `stop`. In one transaction, lock each matching `Doctor` row in primary-key order, clear
  `whatsapp_opt_in` and audit it (`whatsapp_reply`). A message older than `whatsapp_opt_in_at` is
  ignored, so a retried old stop cannot undo a newer opt-in. Rows already waiting then go to email
  through the `OPTED_OUT` check. Stopping applies in every mode, including `off`.
- **Confirmation:** only if an opt-in actually changed, reply
  `تم إيقاف رسائل واتساب، وستصلك الإشعارات على بريدك الإلكتروني. يمكنك إعادة التفعيل من صفحة حسابك.`
- **Help:** any other message, at most once per 24 hours per doctor (`whatsapp_help_sent_at`), gets
  `لإيقاف الرسائل أرسل: إيقاف. لأي استفسار يرجى تسجيل الدخول إلى حسابك.`

Repeats are harmless by design, so no message table is needed: a repeated stop changes nothing, and
the timestamp limits help replies.

**How replies are sent:** free text with `send_text()` after the commit, at most one per request,
with `timeout=(2, 3)`. A failure is logged by code and not retried, and never changes the 200. This
is the one provider call outside the job, because a queued reply would need the phone number stored.
`off` mode sends no replies and `allowlist` replies only to listed numbers. Whether Meta accepts the
free-text reply inside its customer-service window is `NOT VERIFIED` until phase 3.

A stop moves notifications to email; it does not end them. They concern the doctor's own application.

## 8. Message content

`notifications/templates.py` is the one table for both channels: event → Meta template name, email
title, body. Each row is an Arabic (`ar`), utility-category template needing Meta approval.

Every message ends with `يرجى تسجيل الدخول إلى حسابك لمعرفة التفاصيل.` WhatsApp adds the footer
`لإيقاف الرسائل أرسل: إيقاف` and a button `فتح الطلب` linking to the application base URL.

| # | Meta template | Email title | Body (`{{1}}` reference number, `{{2}}` amount) |
|---|---|---|---|
| 1 | `med_application_received` | تم استلام طلبك | تم استلام طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم، وسيتم مراجعته. |
| 2 | `med_correction_needed` | مطلوب استكمال بيانات | طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم يحتاج إلى استكمال بعض البيانات. |
| 3 | `med_application_approved` | تم قبول طلبك | تم قبول طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم. |
| 4 | `med_application_rejected` | تم رفض طلبك | تم رفض طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم. |
| 5 | `med_payment_confirmed` | تم تأكيد السداد | تم تأكيد سداد الرسوم الخاصة بطلبك رقم {{1}}. |
| 6 | `med_payment_receipt_rejected` | لم يتم قبول الإيصال | لم يتم قبول إيصال السداد الخاص بطلبك رقم {{1}}. |
| 7 | `med_dues_requested` | مطلوب سداد مستحقات | مطلوب سداد مستحقات نقابية بقيمة {{2}} لاستكمال طلبك رقم {{1}}. |
| 8 | `med_dues_confirmed` | تم تأكيد سداد المستحقات | تم تأكيد سداد المستحقات النقابية بقيمة {{2}} الخاصة بطلبك رقم {{1}}. |
| 9 | `med_dues_receipt_rejected` | لم يتم قبول إيصال المستحقات | لم يتم قبول إيصال سداد المستحقات النقابية بقيمة {{2}} الخاصة بطلبك رقم {{1}}. |
| 10 | `med_dues_cancelled` | تم إلغاء طلب المستحقات | تم إلغاء طلب سداد المستحقات النقابية بقيمة {{2}} الخاص بطلبك رقم {{1}}. |

**Rules:**
- The only variables are the reference number and, for events 7–10, the amount. Rejection reasons,
  correction notes and the dues reason stay behind login.
- The amount (owner decision) is read from `SyndicateDuesRequest.amount` at send time and formatted
  like the UI: `3٬025 ج.م`, with decimals only when not whole.
- An application can have several open dues requests, so no message may imply all dues are settled
  or that nothing more is owed. The amount shows which request is meant. Two requests for the same
  amount read alike, which is still true, and the portal shows what remains.
- Event 6 does not tell the doctor to upload a new receipt. Whether they can depends on the
  application status, so the portal explains it.
- Email subject: `طلبك رقم {reference}: {title}`. Sender: `notifications@neqabacare.com`.
- The phone is converted from stored `01XXXXXXXXX` to `+201XXXXXXXXX` at send time. The database
  keeps the current format.

## 9. API and screens

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET/PUT | `/api/v1/profile/notifications/` | doctor (own) | read or set `whatsapp_opt_in` |
| GET | `/api/v1/admin/applications/{id}/notifications/` | admin | history for the panel |
| POST | `/api/v1/admin/applications/{id}/notifications/{nid}/resend/` | admin | new row with the same event |

- **Opt-in has its own endpoint and service.** `ensure_profile_editable` freezes the profile while an
  application is in review, and a doctor must be able to change consent at any time. The service
  locks the `Doctor` row, as `update_profile` does, so a save in one cannot undo the other.
- **Opting in requires a valid mobile**, otherwise the standard validation error.
- **Consent is only asked where WhatsApp can send.** The GET returns `whatsapp_available`, true when `NOTIFICATIONS_MODE` is `allowlist` or `live` (`doctors.services.whatsapp_available`, over the `SENDING_MODES` in `notifications/modes.py` that the sender also uses). `set_whatsapp_opt_in(enabled=True)` raises a validation error on `whatsapp_opt_in` when it is false; opting out is always allowed. The status-page prompt is hidden when it is false, and the profile section is hidden unless the doctor is already opted in, so they can still opt out.
- **Changing the phone clears the opt-in:** `update_profile` resets it when the normalized number
  changes, because consent was given for the old number.
- **Resend** re-runs the routing in section 5 and records `created_by` and an audit entry. It returns
  409 in two cases, both checked under the application lock:
  - a row for the same application, event and dues request is `PENDING` or `SENDING`, or is a
    WhatsApp `SENT` row still inside the delivery timeout, whose email could otherwise add a second
    message;
  - `still_relevant` is false, because the action is no longer needed.

  It is throttled per admin (`notification_resend`).
- Doctors never see `Notification` rows. Status, attempts and provider fields are read-only for
  everyone; only `services.py` writes them.

**Frontend** (all strings in `i18n/ar.ts`, event and status labels from reference data):
- `NotificationsPanel` in `features/admin`, beside `DuesPanel`: event, channel, status, time, masked
  recipient, Arabic explanation of the error, Resend with a confirmation dialog. Failed and expired
  rows are visually prominent, and `SUPERSEDED` rows are shown quietly as no longer needed. A `SENT`
  email reads `قبله مزوّد البريد، والتسليم غير مؤكد`, never as delivered.
- `ProfilePage`: opt-in checkbox beside the phone field showing the number it applies to, and still
  usable when the rest of the profile is frozen. The paper-form replica does not change.
- Status page: a prompt to opt in for doctors not yet opted in, dismissible and remembered in
  `localStorage` under a key that includes the doctor ID, so a shared browser does not hide it from
  another doctor. Doctors who never open the profile still see it.

## 10. Configuration and infrastructure

Names only; no values in Git.

| Setting | Where |
|---|---|
| `NOTIFICATIONS_MODE`, `NOTIFICATION_PROVIDERS`, `NOTIFICATION_MAX_AGE_HOURS`, `WHATSAPP_DELIVERY_TIMEOUT_MINUTES`, `NOTIFICATION_RESEND_RATE_LIMIT` | plain env |
| `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`, `SES_REGION`, `SES_FROM_ADDRESS`, `NOTIFICATION_BASE_URL`, `AWS_ROLE_ARN` | plain env |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `NOTIFICATIONS_ALLOWLIST` | Key Vault secret references |

`NOTIFICATIONS_MODE`, `NOTIFICATIONS_ALLOWLIST` and the WhatsApp settings go on both the `notify` job
and the web app.

**Logging filter (`config/logging.py`, a second line of defence behind allowlisted logs):**
- `_DIGIT_RUN` only masks runs of 14 or more digits, which misses `2010…` phone numbers (12 digits).
  Lower it to 11 or more. Occasionally masking another long number is acceptable.
- Also mask email addresses, and Egyptian mobiles written with spaces or hyphens. Match the mobile
  shape rather than any digit group, so dates and IDs are not hit.

`config/telemetry.py` uses the same function, so exported logs and spans are covered too. The rule
against logging payloads stays.

**AWS (`eu-north-1`, the selected Region, confirmed by the owner on 2026-11-03):**
- SES in this Region was still in the sandbox when this was written (checked 2026-11-02).
- Domain identity for `neqabacare.com` with DKIM, custom MAIL FROM and DMARC. Records go in Cloudflare
  as DNS only (not proxied).
- Production access request, sent only after the domain is verified and the owner agrees.
- IAM role allowing only `ses:SendEmail` on that identity.
- CloudWatch alarms on `Reputation.BounceRate` and `Reputation.ComplaintRate`.

**Monitored mailbox:** SES forwards bounce and complaint feedback by email, so
`notifications@neqabacare.com` must reach a person. Forward it to a mailbox the owner chooses with
Cloudflare Email Routing (`NOT VERIFIED`; check it does not conflict with existing MX records). This
is the operational signal for sender reputation, not per-notification tracking.

**Credentials from Azure to AWS:** the job's managed identity assumes the IAM role through OIDC
federation, so no AWS secret exists. `AWS_ROLE_ARN` alone is not enough: boto3 also needs a source
for the web-identity token, which the spike in section 12 must settle. If the spike fails, the
fallback is an access key in Key Vault with a rotation note.

**Meta:** business portfolio, dedicated phone number, app with a system-user token, webhook
subscription for both `statuses` and `messages`, 10 templates.

## 11. Open items

- **L3 (cross-border transfer) and L4 (retention)** in `docs/security.md` must be extended to cover
  Meta and AWS as new recipients of phone numbers and email addresses. Owner and legal sign-off is
  required before `live` in production. It does not block building.
- **Retention:** 12 months is proposed under L4. This version implements no automatic purge, because
  the retention period is not decided. Rows are small, and a purge step in the `cleanup` job is simple
  to add once it is.
- **Cost:** the Meta rate for Egypt is not yet confirmed; check Meta's rate card before launch. The
  5-minute job is roughly a fifth of the 1-minute estimate ($10–15 a month), not yet priced.
- **Stop requests made outside WhatsApp:** Meta's policy also covers requests made off WhatsApp, such
  as a phone call. This version gives the doctor the profile checkbox but gives staff no control.
  Decide whether staff need one.
- **Meta business ownership:** the owner decides which legal entity the WhatsApp business and display
  name belong to.
- **Existing telemetry gap, not part of this work:** from reading the code, the `cleanup` and
  `migrate` jobs set `OTEL_SERVICE_NAME` but never start telemetry, so their logs reach only the
  console. Not tested on Azure.

## 12. Testing and rollout

**Backend (test-first, on PostgreSQL):**
- A rolled-back change leaves no row; a committed one leaves exactly one, for each of the 10 events.
- A second correction on one application sends again.
- Every row of the section 4 transition table, and rejection of every change not in it.
- Every fallback trigger in section 5, including `SEND_INTERRUPTED` and `UNKNOWN_RESULT`: a fake that
  accepts and then times out goes to email on WhatsApp and retries on email.
- Relevance, for each row of the section 2 table: for example create dues, force a retry, cancel, and
  assert the payment request never sends on either channel; repeat after a pause in `off` mode.
- Claim safety: two workers racing for one row make one provider call, and the test fails if the
  locking is removed.
- Claim progress: with row A locked, another worker claims due row B without waiting. These are
  separate tests because removing only `skip_locked` keeps the row safe but makes workers wait.
- A delivery timeout and a `delivered` webhook racing never produce `DELIVERED` → `FAILED`, and a
  crash between parent and fallback leaves neither change committed.
- A stale send result does not overwrite a recovery decision.
- One email per failed row under a webhook and job race.
- Expiry: a fallback inherits `expires_at`, and a resend gets a new one only after the relevance check.
- Budget: email rows go first, and 5 temporary errors stop one provider but not the other.
- Webhook: bad signature, wrong `hub.mode`, wrong `phone_number_id`, repeats, every cell of the section
  7 table, unknown IDs, and a 500 with no acknowledgement when the database fails.
- Stop and help: each stop word, a sentence containing "stop" (help, not stop), two doctors sharing a
  number, an old stop after a newer opt-in, the 24-hour help limit, an unknown number, each mode, and
  a failed reply still returning 200.
- Two dues requests on one application: confirming, rejecting or cancelling one produces wording that
  cannot be read as resolving the other, on both channels.
- Privacy: seed an email address and contiguous, international, formatted and Eastern Arabic phone
  numbers into provider exceptions, `extra` fields and span attributes. None reach a log or export
  path, and notification IDs and error codes survive.
- Phone change clears the opt-in; the opt-in works on a frozen profile.
- `off`, `allowlist` (WhatsApp, direct email and fallback each) and `live` modes; `live` with fake
  providers refuses to start in production settings; expiry; resend conflict scoped to the dues
  request; object permissions on every endpoint.
- The `send_notifications` entrypoint starts telemetry before Django builds its logging handlers.

**Frontend:** panel, Resend, `SENT` email wording, opt-in and prompt tests including the per-doctor
`localStorage` key, plus `rtl_check.py frontend/src`.

**Migrations:** add-only and reviewed with `django-safe-migration`.

**Rollout:** phases 1 and 2 can overlap, because provider reviews take days.

| Phase | Work | Exit condition |
|---|---|---|
| 0. Spikes on dev (throwaway) | (a) A signed POST through the Static Web App `/api` proxy: do the header and raw body arrive unchanged? If not, Meta calls the Container App address directly. Check the body limit against Meta's maximum. (b) OIDC federation from the `notify` job's managed identity to an IAM role under this project's managed policies: issuer, audience and subject limits, token source and refresh, a bounded credential fetch, and a real `ses:SendEmail` authorization | Both answered and recorded |
| 1. Provider setup | SES domain and DNS, monitored mailbox, production access request, Meta onboarding, webhook subscription, template submission with the section 8 wording | Domain verified; **SES production access approved in the selected Region** with a quota suited to launch; templates approved |
| 2. Code | Backend, then frontend | Tests, `ruff` and RTL check pass |
| 3. Dev trial | `allowlist` with the owner's numbers, including one without WhatsApp to exercise the real fallback | Each event seen on a real device or inbox; a real stop and help reply work; a provider failure reaches each alert; a paused job raises the missed-run alert |
| 4. Production | L3 and L4 signed off, real providers selected, phase 1 confirmed for production, then `live` | Owner decision |

Creating Azure, AWS or Meta resources, pushing, and sending real messages each require explicit owner
confirmation at that step. Anything not exercised against the real service is reported as
`NOT VERIFIED`.

**Stopping:** set `NOTIFICATIONS_MODE=off` on the job and the web app. Status changes keep working,
rows wait until they expire, and on resuming each row passes the relevance check before it sends.

## 13. Third-party audit outcome

The audit is `2026-11-02-notifications-audit.md`. Its diagnoses were checked against this repository
and the providers' documentation. Where its suggested fix was heavier than the problem needed, this
design takes the smaller fix below.

| ID | Outcome | Where it landed, or why it did not |
|---|---|---|
| F01 | **Not adopted** | Rated too high: not a lost notification, only an extra email or a later fallback. The delivery timeout and `SEND_INTERRUPTED` bound it. Accepted in section 5. No callback inbox |
| F02 | Adopted | One `apply_transition()` service, claim check through `attempts`, lock order (section 4) |
| F03 | Adopted, simplified | `still_relevant` at claim and `SUPERSEDED` (section 2). No source revisions |
| F04 | Adopted in part | Accurate label and a monitored mailbox (sections 9, 10). Per-notification bounce tracking stays out, as the owner decided |
| F05 | Adopted | Stop and help replies, new footer (sections 7, 8) |
| F06 | **Not adopted** | Rated too high: needs a stale tab submitting after a phone change in another tab. Accepted risk. The shared `Doctor` lock is kept (section 9). No contact version |
| F07 | Adopted | Amount in events 8–10; "no need to pay" removed (section 8) |
| F08 | Adopted | Telemetry before Django, flush, oldest-due and missed-run alerts (section 6) |
| F09 | Adopted | Full transition table (section 4) |
| F10 | Adopted | `UNKNOWN_RESULT` goes to email; at-least-once stated (sections 1, 5) |
| F11 | Adopted, simplified | Conflict scoped to the dues request, plus `SENT` and relevance checks (section 9). No occurrence table or idempotency key |
| F12 | Adopted, simplified | Connect and read timeouts, one SDK attempt, stop claiming near the budget (section 6). No total-deadline handling |
| F13 | Adopted, simplified | Email first, per-provider stop after 5 errors, oldest-due alert (section 6). No latency objective, jitter or circuit breaker |
| F14 | Adopted | Allowlisted logs, translated errors, wider filter, narrowed claim (sections 1, 6, 10) |
| F15 | Adopted | Production access in the phase 1 exit; `live` refuses fakes (sections 6, 12) |
| F16 | Adopted | `expires_at` inherited by fallbacks; a resend sets it deliberately (section 5) |
| F17 | Adopted | Separate safety and progress tests (section 12) |

## 14. Email-first operation (owner decision, 2026-11-04)

Amazon SES is in production (50,000 a day, 14 a second, the sending domain verified in the selected
Region). WhatsApp onboarding is stopped because the Meta business profile is unfinished. Email is
therefore the only channel in use. No WhatsApp code is deleted: it stays, switched off.

**The switch.** `WHATSAPP_ENABLED` (bool, default `false`; pinned `true` in test settings so the
WhatsApp tests keep their meaning).

**What changes while it is off:**

- `first_channel()` returns `EMAIL` for every doctor, whatever their opt-in.
- `whatsapp_available()` is false, so the API reports `whatsapp_available: false`, the status-page
  prompt and the profile section hide themselves, and opting in is refused. Opting out stays allowed.
- A `WHATSAPP` row still `PENDING` (created before the switch went off) is not lost. At claim,
  right after the relevance check and before the allowlist check, it becomes `FAILED` with
  `WHATSAPP_DISABLED`, uses no attempt, and gets its fallback email through `apply_transition`.
  The email row then passes its own checks (allowlist included). No WhatsApp client is built.
- `run_once` runs the WhatsApp pass first (it only settles leftovers), then the email pass, so the
  fallback goes out in the same run.
- Production settings require `SES_REGION`, `SES_FROM_ADDRESS` and `NOTIFICATION_BASE_URL` for a
  sending mode with real providers, and the five `WHATSAPP_*` settings only when the switch is on.
- Task 14 (federation) is not built, so the default boto3 chain is the only credential path. With a
  sending mode and real providers production also requires `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY` and refuses to start without them (naming the setting, never a value).
  This check goes away with Task 14. Long-lived keys are the spec's fallback and should be rotated;
  federation remains the preferred path.
- Bicep: `enableWhatsApp` (default `false`) controls the `whatsapp-*` Key Vault references, the
  `WHATSAPP_*` plain settings and `WHATSAPP_ENABLED`. `notifications-allowlist` is referenced only
  in `allowlist` mode. `sesAccessKeyFromKeyVault` (default `false`) injects `aws-access-key-id` and
  `aws-secret-access-key` as environment variables, for the app and the notify job only.

**Turning WhatsApp on later:** finish the Meta setup (section 12 phase 1), create the three
`whatsapp-*` secrets, deploy with `enableWhatsApp=true` and the phone number ID and API version, and
the app starts with `WHATSAPP_ENABLED=true`. On a first switch-on, doctors are asked for consent from the
status page. A doctor still opted in from an earlier on period is not asked and goes straight back to
WhatsApp, even if they sent a stop reply while parked (that reply gets a 403 and changes nothing).
Nobody is affected today. Everything in sections 5 to 8 applies as written. Nothing here is verified against
Azure, AWS or Meta (`NOT VERIFIED`).
