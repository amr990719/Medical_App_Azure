# Design: doctor notifications (WhatsApp first, email fallback)

**Date:** 2026-11-02
**Status:** awaiting owner review of this document
**Providers (owner decision):** Meta WhatsApp Cloud API and Amazon SES (not Azure Communication Services)

## 1. Goal

When an admin or the system changes something a doctor must act on or wants to know, the doctor is
told on WhatsApp. If WhatsApp cannot reach them, or they have not opted in, they are told by email
at their registered address.

**Success means:**
- A status change and its notification commit together, or neither does.
- An outage at Meta or AWS never blocks or rolls back an admin action.
- A WhatsApp failure reported minutes later still produces the email.
- An admin can see on the application page whether the doctor was told, and resend.
- No message text, full phone number or full email address is stored or logged.

**Out of scope for this version:** free-text messages from admins, handling doctors' WhatsApp
replies, SES bounce tracking, phone verification codes, SMS, scheduled reminders, automatic purge
of old rows (section 11).

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

## 3. Data model

New app: `apps/notifications`. All PKs are UUIDs and foreign keys use `PROTECT`, as elsewhere.

### `Notification` (one row per channel attempt chain)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `application` | FK `InsuranceApplication` | required |
| `dues_request` | FK `SyndicateDuesRequest`, nullable | events 7–10; supplies the amount for event 7 at send time |
| `event` | choices | section 2 |
| `channel` | choices | `WHATSAPP`, `EMAIL` |
| `status` | choices | section 4 |
| `provider_message_id` | char, nullable | Meta `wamid` or SES `MessageId` |
| `attempts` | small int | default 0 |
| `next_attempt_at` | datetime | when the row becomes due |
| `sending_started_at` | datetime, nullable | detects interrupted sends |
| `error_code` | char, blank | provider code or an internal code; never provider free text |
| `recipient_masked` | char, blank | filled at send: `010•••••678` or `a•••@example.com` |
| `fallback_of` | one-to-one self FK, nullable | the WhatsApp row this email replaces |
| `created_by` | FK user, nullable | the admin for a resend; null for automatic rows |
| `created_at`, `sent_at`, `delivered_at`, `updated_at` | datetime | |

**Constraints and indexes:**
- `CHECK` on `event`, `channel` and `status` values.
- Unique `provider_message_id` where not null, which is how the webhook finds a row.
- `fallback_of` is one-to-one, so a database constraint guarantees at most one email per failed
  WhatsApp row even if the webhook and the job race. `IntegrityError` is handled as "already done".
- Partial index on `(next_attempt_at)` where status is `PENDING`.
- Partial index on `(sent_at)` where channel is `WHATSAPP` and status is `SENT`.
- Index on `(application, created_at)`.

**No uniqueness on event and application.** A second correction request on the same application
must send again. Duplicates are prevented because `enqueue()` runs once per change and retries
reuse the same row.

### `Doctor` additions

- `whatsapp_opt_in` boolean, `db_default=False`.
- `whatsapp_opt_in_at` datetime, nullable.

Existing doctors are not opted in, so they receive email until they opt in.

### Audit

New `AuditAction` values: `WHATSAPP_OPT_IN_CHANGED`, `NOTIFICATION_RESENT`. Metadata holds IDs and
booleans only, never a phone number or address. Automatic sends are not audited; the `Notification`
row is their record.

## 4. Status lifecycle

```text
PENDING → SENDING → SENT → DELIVERED   (DELIVERED is WhatsApp only; SENT is final for email)
                 ↘ FAILED
PENDING → EXPIRED      older than NOTIFICATION_MAX_AGE_HOURS
PENDING → SUPPRESSED   allowlist mode and the recipient is not listed; no fallback
```

## 5. Routing and fallback

`enqueue()` picks the first channel: `WHATSAPP` if the doctor has opted in and the phone is a valid
mobile, otherwise `EMAIL`.

A WhatsApp row ends as `FAILED` and gets a linked email row (`fallback_of`) in each of these cases:

| Trigger | `error_code` |
|---|---|
| Opt-in withdrawn or phone invalid at send time (checked again before sending) | `OPTED_OUT` |
| Meta returns a permanent error (4xx other than 429) | Meta's code |
| A temporary error (timeout, connection error, 5xx, 429) continues after 3 attempts | Meta's code or `TIMEOUT` |
| Webhook reports `failed` | Meta's code, e.g. `131026` |
| Still `SENT` with no `delivered` after `WHATSAPP_DELIVERY_TIMEOUT_MINUTES` (default 30) | `NO_DELIVERY_RECEIPT` |
| Row stuck in `SENDING` longer than 10 minutes (sender crashed) | `SEND_INTERRUPTED` |

**Why a crashed send goes to email, not back to WhatsApp:** the first attempt may have reached the
doctor. At worst they get the same news on both channels, which is harmless, while a second
WhatsApp retry could repeat indefinitely.

**Retry timing:** the second attempt is due 5 minutes after the first and the third 15 minutes after
the second. Email uses the same temporary-error rule. An email row that runs out of attempts, gets a
permanent error or is stuck in `SENDING` ends as `FAILED` with no further fallback, and the admin
panel shows it.

**Known and accepted:** a doctor whose phone is off for over 30 minutes may receive both messages.

## 6. Sender

`manage.py send_notifications` runs as a scheduled Container Apps job named `notify`, modelled on
`cleanupJob` in `infrastructure/modules/container-app.bicep`, with a new `notify` mode in
`backend/entrypoint.sh`.

- **Schedule:** `notifyCron` parameter, default `*/5 * * * *`. `replicaTimeout` 280 seconds so one
  run ends before the next starts. Overlap would still be safe (below).
- **Each run, in order:**
  1. Mark overdue `PENDING` rows `EXPIRED` (default 72 hours).
  2. Recover rows stuck in `SENDING`.
  3. Apply the delivery timeout to `SENT` WhatsApp rows.
  4. Send due rows, up to 200 per run or a 240-second budget.
- **Claiming a row:** a short transaction uses `select_for_update(skip_locked=True)`, sets
  `SENDING`, `sending_started_at` and increments `attempts`, then commits. The provider call happens
  **outside** any transaction, with a 10-second timeout. A second transaction records the outcome.
- **No immediate send after commit.** The job is the only send path, so admin requests never wait on
  a provider. A doctor may wait up to 5 minutes.
- **`NOTIFICATIONS_MODE`:**
  - `off` (default): only step 1 runs. Rows still accumulate and expire.
  - `allowlist`: sends only to `NOTIFICATIONS_ALLOWLIST`, others become `SUPPRESSED`. Dev uses this.
  - `live`: sends to everyone. Production settings refuse `live` if a required provider setting is
    missing.
- **Logging:** the run logs counts and notification IDs only. `FAILED` and `EXPIRED` log at `WARNING`
  with the event and error code, which is what the alert uses.

### Provider clients

`notifications/providers.py` defines `WhatsAppClient.send_template()` and `EmailClient.send()`. Both
return a provider message ID or raise `TemporaryProviderError` or `PermanentProviderError`. Tests and
local development use fakes selected by setting.

- **WhatsApp:** `requests` (already a dependency) against the Graph API, with the version pinned in a
  setting.
- **Email:** `boto3` (new dependency) with the SES v2 API, in the selected Region, HTML plus plain
  text, UTF-8.

## 7. WhatsApp webhook

`/api/v1/notifications/whatsapp/webhook/`, with no session authentication and no CSRF.

- **`GET`:** Meta's subscription handshake. It checks `hub.verify_token` and returns `hub.challenge`.
- **`POST`:**
  1. Verify `X-Hub-Signature-256` as HMAC-SHA256 of the **raw body** with the app secret, using a
     constant-time comparison. Failure returns 403 and nothing is parsed.
  2. For each entry in `statuses`, find the row by `provider_message_id` and apply the table below.
  3. Ignore everything else, including inbound messages and unknown IDs.
  4. Return 200.

| Webhook status | Row in `SENT` | Row in `DELIVERED` | Row in `FAILED` |
|---|---|---|---|
| `sent` | no change | no change | no change |
| `delivered`, `read` | → `DELIVERED` | no change | → `DELIVERED`; an email already created still sends |
| `failed` | → `FAILED` + email row | no change | no change |

Meta retries for up to 7 days and events can arrive out of order, so every branch must be safe to
repeat. The endpoint updates notification rows only and returns no data.

**Payloads must never be logged**, because they contain phone numbers.

## 8. Message content

`notifications/templates.py` is the one table for both channels: event → Meta template name, email
title, body. Each row is an Arabic (`ar`), utility-category template needing Meta approval.

Every message ends with `يرجى تسجيل الدخول إلى حسابك لمعرفة التفاصيل.` WhatsApp adds
`هذا الرقم لا يستقبل الردود.` and a button `فتح الطلب` linking to the application base URL.

| # | Meta template | Email title | Body (`{{1}}` reference number, `{{2}}` amount) |
|---|---|---|---|
| 1 | `med_application_received` | تم استلام طلبك | تم استلام طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم، وسيتم مراجعته. |
| 2 | `med_correction_needed` | مطلوب استكمال بيانات | طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم يحتاج إلى استكمال بعض البيانات. |
| 3 | `med_application_approved` | تم قبول طلبك | تم قبول طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم. |
| 4 | `med_application_rejected` | تم رفض طلبك | تم رفض طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم. |
| 5 | `med_payment_confirmed` | تم تأكيد السداد | تم تأكيد سداد الرسوم الخاصة بطلبك رقم {{1}}. |
| 6 | `med_payment_receipt_rejected` | لم يتم قبول الإيصال | لم يتم قبول إيصال السداد الخاص بطلبك رقم {{1}}. |
| 7 | `med_dues_requested` | مطلوب سداد مستحقات | مطلوب سداد مستحقات نقابية بقيمة {{2}} لاستكمال طلبك رقم {{1}}. |
| 8 | `med_dues_confirmed` | تم تأكيد سداد المستحقات | تم تأكيد سداد المستحقات النقابية الخاصة بطلبك رقم {{1}}. |
| 9 | `med_dues_receipt_rejected` | لم يتم قبول إيصال المستحقات | لم يتم قبول إيصال المستحقات النقابية الخاص بطلبك رقم {{1}}. |
| 10 | `med_dues_cancelled` | تم إلغاء طلب المستحقات | تم إلغاء طلب سداد المستحقات النقابية الخاص بطلبك رقم {{1}}، ولا حاجة إلى السداد. |

**Rules:**
- The only variables are the reference number and, for event 7, the amount. Rejection reasons,
  correction notes and the dues reason stay behind login.
- The amount (owner decision) is read from `SyndicateDuesRequest.amount` at send time and formatted
  like the UI: `3٬025 ج.م`, with decimals only when not whole.
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
  application is in review, and a doctor must be able to change consent at any time.
- **Opting in requires a valid mobile**, otherwise the standard validation error.
- **Changing the phone clears the opt-in:** `update_profile` resets it when the normalized number
  changes, because consent was given for the old number.
- **Resend** re-runs the routing in section 5 and records `created_by` and an audit entry. It returns
  409 while a row for the same application and event is `PENDING` or `SENDING`, checked under the
  application lock, and is throttled.
- Doctors never see `Notification` rows. Status, attempts and provider fields are read-only for
  everyone; only `services.py` writes them.

**Frontend** (all strings in `i18n/ar.ts`, event and status labels from reference data):
- `NotificationsPanel` in `features/admin`, beside `DuesPanel`: event, channel, status, time, masked
  recipient, Arabic explanation of the error, Resend with a confirmation dialog. Failed and expired
  rows are visually prominent.
- `ProfilePage`: opt-in checkbox beside the phone field showing the number it applies to, and still
  usable when the rest of the profile is frozen. The paper-form replica does not change.
- Status page: a prompt to opt in for doctors not yet opted in, dismissible and remembered in
  `localStorage`, so doctors who never open the profile still see it.

## 10. Configuration and infrastructure

Names only; no values in Git.

| Setting | Where |
|---|---|
| `NOTIFICATIONS_MODE`, `NOTIFICATION_MAX_AGE_HOURS`, `WHATSAPP_DELIVERY_TIMEOUT_MINUTES` | plain env |
| `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`, `SES_REGION`, `SES_FROM_ADDRESS`, `NOTIFICATION_BASE_URL`, `AWS_ROLE_ARN` | plain env |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `NOTIFICATIONS_ALLOWLIST` | Key Vault secret references |

**Logging filter:** `_DIGIT_RUN` in `config/logging.py` only masks runs of 14 or more digits, which
misses `2010…` phone numbers (12 digits). Lower it to 11 or more digits so numbers are masked if one
ever reaches a log by mistake. The rule against logging payloads stays.

**AWS (`eu-north-1`, to be confirmed as the selected Region in AWS Settings):**
- Domain identity for `neqabacare.com` with DKIM, custom MAIL FROM and DMARC. Records go in Cloudflare
  as DNS only (not proxied).
- Production access request, sent only after the domain is verified and the owner agrees.
- IAM role allowing only `ses:SendEmail` on that identity.
- CloudWatch alarm on `Reputation.BounceRate`.

**Credentials from Azure to AWS:** the Container App's managed identity assumes the IAM role through
OIDC federation, so no AWS secret exists. If the spike in section 12 fails, the fallback is an access
key in Key Vault with a rotation note.

**Meta:** business portfolio, dedicated phone number, app with a system-user token, webhook
subscription, 10 templates.

**Alerts:** Application Insights on `FAILED`/`EXPIRED` warnings and on `notify` job failures.

## 11. Open items

- **L3 (cross-border transfer) and L4 (retention)** in `docs/security.md` must be extended to cover
  Meta and AWS as new recipients of phone numbers and email addresses. Owner and legal sign-off is
  required before `live` in production. It does not block building.
- **Retention:** 12 months is proposed under L4. This version implements no automatic purge, because
  the retention period is not decided. Rows are small, and a purge step in the `cleanup` job is simple
  to add once it is.
- **Cost:** the Meta rate for Egypt is not yet confirmed; check Meta's rate card before launch. The
  5-minute job is roughly a fifth of the 1-minute estimate ($10–15 a month), not yet priced.
- **Sender mailbox:** nothing receives mail at `notifications@neqabacare.com`. Decide whether replies
  should go anywhere.
- **Meta business ownership:** the owner decides which legal entity the WhatsApp business and display
  name belong to.

## 12. Testing and rollout

**Backend (test-first, on PostgreSQL):**
- A rolled-back change leaves no row; a committed one leaves exactly one, for each of the 10 events.
- A second correction on one application sends again.
- Every fallback trigger in section 5, including `SEND_INTERRUPTED`.
- Two concurrent senders never claim the same row (threaded test, as for `transition()`), with a
  mutation check that removing `skip_locked` claiming makes the test fail.
- One email per failed row under a webhook and job race.
- Webhook: bad signature, repeats, every cell of the section 7 table, unknown IDs, inbound messages.
- No phone number, address or payload in logs.
- Phone change clears the opt-in; the opt-in works on a frozen profile.
- `off`, `allowlist` and `live` modes; expiry; resend conflict; object permissions on every endpoint.

**Frontend:** panel, Resend, opt-in and prompt tests, plus `rtl_check.py frontend/src`.

**Migrations:** add-only and reviewed with `django-safe-migration`.

**Rollout:**

| Phase | Work | Exit condition |
|---|---|---|
| 0. Spikes on dev (throwaway) | (a) A signed POST through the Static Web App `/api` proxy: do the header and raw body arrive unchanged? If not, Meta calls the Container App address directly. (b) OIDC federation from the managed identity to an IAM role under this project's managed policies | Both answered and recorded |
| 1. Provider setup | SES domain and DNS, production access request, Meta onboarding, template submission. Starts early because reviews take days | Domain setup complete, templates approved |
| 2. Code | Backend, then frontend | Tests, `ruff` and RTL check pass |
| 3. Dev trial | `allowlist` with the owner's numbers, including one without WhatsApp to exercise the real fallback | Each event seen on a real device or inbox |
| 4. Production | L3 and L4 signed off, then `live` | Owner decision |

Creating Azure, AWS or Meta resources, pushing, and sending real messages each require explicit owner
confirmation at that step. Anything not exercised against the real service is reported as
`NOT VERIFIED`.

**Stopping:** set `NOTIFICATIONS_MODE=off`. Status changes keep working, and rows wait until they
expire.
