# Doctor Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tell doctors about application, payment and dues changes on WhatsApp, falling back to email, without provider outages ever affecting an admin action.

**Architecture:** A transactional outbox: hooks insert a `Notification` row inside the transaction that changes the application. A scheduled Container Apps job (`manage.py send_notifications`) claims rows with `skip_locked`, calls Meta or SES outside any transaction, and records the outcome through one locked transition service. A signed webhook applies WhatsApp receipts and stop requests.

**Tech Stack:** Django 5 + DRF, PostgreSQL (psycopg 3), `requests` (Meta Graph API), `boto3` (SES v2), Bicep, React + TypeScript + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-11-02-notifications-design.md`. Read it first. Section numbers below refer to it.

## Global Constraints

- All PKs are UUIDs; foreign keys use `PROTECT`. Business logic stays in services, never in views or serializers.
- No message text, full phone number or full email address on notification rows, in logs or in audit metadata. Log only: notification ID, event, channel, status, error code, counts.
- Webhook payloads and inbound message text are never logged or stored.
- Provider calls happen outside database transactions. Clients raise errors carrying a code only, using `raise ... from None`.
- `Decimal` for money, never float. Amount format matches `frontend/src/utils/format.ts::formatAmount`: `1٬250.50 ج.م`, and a zero fraction is dropped (`3٬025 ج.م`).
- Python: ruff line length 100, type hints, pytest + factory_boy, tests in `apps/<app>/tests/`, on PostgreSQL only.
- API: snake_case JSON and the `{"error": {"code", "message", "fields"}}` envelope. `manage.py spectacular --file openapi.yaml --validate --fail-on-warn` must pass.
- Frontend: every string in `frontend/src/i18n/ar.ts`; logical utilities only (`ms-* me-* ps-* pe-* start-* end-*`); `dir="ltr"` on phone values; camelCase in the SPA through the existing mapping layer; no `any`.
- Migrations are add-only and reviewed with the `django-safe-migration` skill.
- Commits use conventional prefixes, one logical change each, and end with the session's attribution line.
- **Never push, open a PR, create Azure/AWS/Meta resources or send a real message without explicit owner confirmation at that step.** Anything not run against the real service is reported as `NOT VERIFIED`.

## Review Focus

1. A doctor whose user account has no email address must end as a visible `FAILED` row with `NO_ADDRESS`, not a crash that stops the run. Test in Task 7.
2. A correctly signed webhook with a malformed or unexpected body must return 200 and change nothing, because Meta's retry cannot fix it. Test in Task 10.
3. The profile can legally hold an incomplete number such as `0101` while drafting. Opt-in must refuse it, routing must pick email, and a stop reply must never match it. Tests in Tasks 4, 9 and 11.
4. A resend URL pairing one application's ID with another application's notification must return 404. Test in Task 12.
5. One webhook batch can mix known, unknown and repeated message IDs. Each entry must be handled independently. Test in Task 10.

## Additions to the spec

The spec leaves these details open. They are decided here so implementers do not have to.

| Item | Decision |
|---|---|
| Doctor has no email | `NO_ADDRESS` as a permanent error on the email row |
| `AWS_WEB_IDENTITY_AUDIENCE` | New plain-env setting, needed by the federation token request |
| `notify_run_failed` | The command logs it at `ERROR` on a fatal exception and re-raises. The fourth alert ("job execution failures") reads this message, and a crash before logging is caught by the missed-run alert |
| `enableNotifications` | New Bicep parameter, default `false`, so deploying before the Key Vault secrets exist cannot break the app |
| SES account-level errors | `SendingPausedException`, `AccountSuspendedException`, `LimitExceededException` and `TooManyRequestsException` are temporary, so an account problem does not permanently fail each row at once |
| Resend errors | New codes `NOTIFICATION_CONFLICT` and `NOTIFICATION_NOT_RELEVANT`, both 409 |

## Owner gates (not agent tasks)

These are spec phases 0, 1, 3 and 4. Each needs explicit owner confirmation. Code tasks do not need them to pass, except Task 14.

| Gate | When | What |
|---|---|---|
| **Phase 0a** | Before Task 17 is deployed | Signed POST through the Static Web App `/api` proxy on dev; check body limit against Meta's maximum |
| **Phase 0b** | **Before Task 14** | OIDC federation from the job's managed identity to an IAM role, with a real `ses:SendEmail` authorization |
| **Phase 1** | Parallel with code | SES domain and DNS, monitored mailbox, production access, Meta onboarding, templates. Submit templates only from the final Task 2 table |
| **Phase 3** | After Task 18 | `allowlist` dev trial on real devices; every alert proven end to end |
| **Phase 4** | Last | L3 and L4 signed off, then `live` |

Work on a local branch `feat/notifications-2026-11-02`, created from `docs/notifications-design`, which holds the spec. Backend commands run from `backend/` with the compose PostgreSQL up (`docs/local-development.md`), and frontend commands from `frontend/`.

---

## File map

```text
backend/apps/notifications/
  models.py          Notification
  formatting.py      amount, phone and mask helpers
  templates.py       the one message table (spec section 8)
  services.py        enqueue, still_relevant, apply_transition, claim_next, record_*, sweeps, resend
  providers.py       WhatsAppClient, EmailClient, fakes, error classes
  aws_auth.py        Azure identity to AWS credentials (gated on phase 0b)
  sender.py          run_once: the job's loop
  webhook.py         signature check and status handling
  inbound.py         stop and help replies
  factories.py
  management/commands/send_notifications.py
  api/{urls,views,serializers}.py
backend/apps/doctors/services.py     set_whatsapp_opt_in, clearing on phone change, stop and help helpers
backend/manage.py                    telemetry before Django for send_notifications
backend/entrypoint.sh                notify mode
backend/config/logging.py            wider masking
backend/config/settings/{base,test,production}.py
infrastructure/modules/{container-app,notification-alerts}.bicep, infrastructure/main.bicep
.github/workflows/reusable-deploy-backend.yml
frontend/src/features/admin/NotificationsPanel.tsx
frontend/src/features/notifications/{useWhatsAppOptIn.ts,WhatsAppOptIn.tsx,WhatsAppPrompt.tsx}
```

---

### Task 1: Data model, enums, settings

**Files:**
- Create: `backend/apps/notifications/__init__.py`, `apps.py`, `models.py`, `factories.py`, `migrations/`, `tests/__init__.py`, `tests/test_models.py`
- Modify: `backend/apps/reference/constants.py`, `backend/apps/reference/api/views.py`, `backend/apps/reference/tests/test_api.py`, `backend/apps/doctors/models.py`, `backend/apps/audit/models.py`, `backend/config/settings/base.py`, `backend/config/settings/test.py`, `backend/requirements/base.txt`, `.env.example`

**Interfaces:**
- Produces: `NotificationEvent`, `NotificationChannel`, `NotificationStatus` (in `apps.reference.constants`); `Notification` with the fields of spec section 3; `apps.notifications.models.DUES_EVENTS: frozenset`; `NotificationFactory`; `Doctor.whatsapp_opt_in`, `whatsapp_opt_in_at`, `whatsapp_help_sent_at`; `AuditAction.WHATSAPP_OPT_IN_CHANGED`, `NOTIFICATION_RESENT`.

- [ ] **Step 1: Write the failing tests** in `tests/test_models.py`

```python
def test_dues_event_requires_a_dues_request():
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(event=NotificationEvent.DUES_REQUESTED, dues_request=None)

def test_non_dues_event_refuses_a_dues_request(): ...      # CHECK fails the other way
def test_fallback_row_must_be_email(): ...                 # fallback_of set + WHATSAPP -> IntegrityError
def test_one_email_per_parent(): ...                       # second row with same fallback_of -> IntegrityError
def test_provider_id_unique_per_channel():
    NotificationFactory(channel="WHATSAPP", provider_message_id="x")
    NotificationFactory(channel="EMAIL", provider_message_id="x")  # allowed
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(channel="WHATSAPP", provider_message_id="x")
def test_null_provider_ids_do_not_conflict(): ...
def test_invalid_status_refused_by_check_constraint(): ...
def test_doctor_opt_in_defaults_to_false(): ...
```

Add to `apps/reference/tests/test_api.py`: `reference_data()` has `notification_events`, `notification_channels`, `notification_statuses`, each a `{value, label}` list with 10, 2 and 8 entries.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications apps/reference/tests/test_api.py -q`
Expected: FAIL at import (`apps.notifications` missing).

- [ ] **Step 3: Add the enums** to `apps/reference/constants.py`, using these exact labels:

| Enum | Value → label |
|---|---|
| `NotificationEvent` | `APPLICATION_RECEIVED` استلام الطلب · `CORRECTION_NEEDED` طلب استكمال بيانات · `APPROVED` قبول الطلب · `REJECTED` رفض الطلب · `PAYMENT_CONFIRMED` تأكيد السداد · `PAYMENT_RECEIPT_REJECTED` رفض إيصال السداد · `DUES_REQUESTED` طلب مستحقات · `DUES_CONFIRMED` تأكيد سداد المستحقات · `DUES_RECEIPT_REJECTED` رفض إيصال المستحقات · `DUES_CANCELLED` إلغاء طلب المستحقات |
| `NotificationChannel` | `WHATSAPP` واتساب · `EMAIL` البريد الإلكتروني |
| `NotificationStatus` | `PENDING` في الانتظار · `SENDING` جارٍ الإرسال · `SENT` تم الإرسال · `DELIVERED` تم التسليم · `FAILED` فشل الإرسال · `EXPIRED` انتهت صلاحيته · `SUPPRESSED` لم يُرسل (وضع الاختبار) · `SUPERSEDED` لم يعد مطلوبًا |

Expose them in `reference_data()` with `_choices`.

- [ ] **Step 4: Add the model, Doctor fields, audit actions and settings**

`Notification` follows spec section 3 exactly, with `error_code` `max_length=40` and these constraint names: `notification_event_valid`, `notification_channel_valid`, `notification_status_valid`, `notification_dues_request_iff_dues_event`, `notification_fallback_is_email`, `uniq_notification_provider_id` (conditional on the ID not being null), plus the partial indexes in the spec. Doctor booleans use `db_default=False`.

Add to `base.py` with `env`: `NOTIFICATIONS_MODE` (`"off"`), `NOTIFICATION_PROVIDERS` (`"fake"`), `NOTIFICATION_MAX_AGE_HOURS` (72), `WHATSAPP_DELIVERY_TIMEOUT_MINUTES` (30), `NOTIFICATIONS_ALLOWLIST` (list, empty), and blank-default strings `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `SES_REGION`, `SES_FROM_ADDRESS`, `NOTIFICATION_BASE_URL`, `AWS_ROLE_ARN`, `AWS_WEB_IDENTITY_AUDIENCE`. Add the throttle rate `"notification_resend": env("NOTIFICATION_RESEND_RATE_LIMIT", default="30/hour")` and `"apps.notifications"` to `INSTALLED_APPS`.

Pin in `test.py`: `NOTIFICATIONS_MODE = "live"`, `NOTIFICATION_PROVIDERS = "fake"`, `WHATSAPP_APP_SECRET = "test-app-secret"`, `WHATSAPP_VERIFY_TOKEN = "test-verify-token"`, `WHATSAPP_PHONE_NUMBER_ID = "111"`, `NOTIFICATION_BASE_URL = "https://example.test"`, `SES_FROM_ADDRESS = "notifications@example.test"`.

Add `boto3>=1.35,<2` to `requirements/base.txt`. Add the names, without values, to `.env.example`.

`NotificationFactory` defaults: `event=APPLICATION_RECEIVED`, `channel=WHATSAPP`, `status=PENDING`, `next_attempt_at=now`, `expires_at=now + 72h`, `application=SubFactory(ApplicationFactory)`.

- [ ] **Step 5: Generate migrations and verify**

Run: `.venv/Scripts/python manage.py makemigrations notifications doctors audit`
Review the files with the `django-safe-migration` skill: `doctors.0003` only adds columns.
Run: `.venv/Scripts/python -m pytest apps/notifications apps/reference apps/doctors -q && .venv/Scripts/python manage.py makemigrations --check`
Expected: PASS; "No changes detected".

- [ ] **Step 6: Commit**

```bash
git add backend .env.example
git commit -m "feat: notification model, enums and settings"
```

---

### Task 2: Formatting and the message table

**Files:**
- Create: `backend/apps/notifications/formatting.py`, `templates.py`, `tests/test_templates.py`

**Interfaces:**
- Produces:
  - `format_amount(amount: Decimal) -> str`
  - `to_e164(local: str) -> str`, from `01XXXXXXXXX` to `+201XXXXXXXXX`
  - `from_whatsapp_sender(raw: str) -> str | None`, from `2010…` to `010…` through `normalize_mobile`
  - `mask_phone(local: str) -> str`, `mask_email(address: str) -> str`
  - `MESSAGES: dict[str, MessageTemplate]` with `meta_name`, `title`, `body`
  - `template_parameters(event, *, reference, amount=None) -> list[str]`
  - `render_email(event, *, reference, amount=None) -> RenderedEmail` (`subject`, `html`, `text`)
  - `STOP_CONFIRMATION: str`, `HELP_REPLY: str`, `CLOSING: str`, `WHATSAPP_FOOTER: str`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("value,expected", [
    ("3025.00", "3٬025 ج.م"), ("1250.50", "1٬250.50 ج.م"), ("250.00", "250 ج.م"),
    ("99999999.99", "99٬999٬999.99 ج.م"),
])
def test_format_amount(value, expected): assert format_amount(Decimal(value)) == expected

def test_masks():
    assert mask_phone("01012345678") == "010•••••678"
    assert mask_email("ahmed@example.com") == "a•••@example.com"

def test_to_e164(): assert to_e164("01012345678") == "+201012345678"

@pytest.mark.parametrize("raw,expected", [
    ("201012345678", "01012345678"), ("+201012345678", "01012345678"),
    ("14155552671", None), ("", None),
])
def test_from_whatsapp_sender(raw, expected): ...

def test_every_event_has_a_message(): assert set(MESSAGES) == set(NotificationEvent.values)

@pytest.mark.parametrize("event", DUES_EVENTS)
def test_dues_messages_carry_the_amount(event):
    assert "{{2}}" in MESSAGES[event].body
    assert template_parameters(event, reference="MED-2026-000123", amount=Decimal("3025")) == [
        "MED-2026-000123", "3٬025 ج.م"]

def test_non_dues_messages_only_carry_the_reference(): ...  # no {{2}}; one parameter

def test_no_message_claims_nothing_is_owed():
    assert all("لا حاجة" not in m.body for m in MESSAGES.values())

def test_footer_replaces_the_no_replies_line():
    assert WHATSAPP_FOOTER == "لإيقاف الرسائل أرسل: إيقاف"
    assert len(WHATSAPP_FOOTER) <= 60  # Meta's footer limit, NOT VERIFIED for this API version

def test_email_subject_and_escaping():
    email = render_email(NotificationEvent.APPROVED, reference="MED-2026-000123")
    assert email.subject == "طلبك رقم MED-2026-000123: تم قبول طلبك"
    assert 'dir="rtl"' in email.html and CLOSING in email.text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_templates.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Implement both modules**

Copy the body table and closing line from spec section 8 verbatim, and the two reply strings from spec section 7. Escape substituted values in `html` with `django.utils.html.escape`. The HTML body is `<div dir="rtl" lang="ar">` holding the body, the closing line and a link to `NOTIFICATION_BASE_URL`. Masks use `MASK_CHAR` from `config.logging`.

- [ ] **Step 4: Run the tests**

Expected: PASS.

- [ ] **Step 5: Commit**: `feat: notification message table and formatting`

---

### Task 3: The transition service

**Files:**
- Create: `backend/apps/notifications/services.py`, `tests/test_transitions.py`

**Interfaces:**
- Consumes: `Notification`.
- Produces:

```python
def apply_transition(
    notification_id, *, to_status: str, expected_attempts: int | None = None,
    error_code: str = "", provider_message_id: str | None = None, recipient_masked: str = "",
    next_attempt_at: datetime | None = None, attempts_delta: int = 0, now: datetime | None = None,
) -> Notification | None
```

It returns the updated row, or `None` when the change is not allowed. A refusal is an expected outcome of a race, not an exception.

- [ ] **Step 1: Write the failing tests**

```python
ALLOWED = [("PENDING","EXPIRED"), ("PENDING","SUPERSEDED"), ("PENDING","SUPPRESSED"),
           ("PENDING","FAILED"), ("PENDING","SENDING"), ("SENDING","SENT"), ("SENDING","PENDING"),
           ("SENDING","FAILED"), ("SENT","DELIVERED"), ("SENT","FAILED"), ("FAILED","DELIVERED")]

@pytest.mark.parametrize("start,target", ALLOWED)
def test_allowed_change_applies(start, target): ...

@pytest.mark.parametrize("start,target", [
    p for p in itertools.product(NotificationStatus.values, repeat=2) if p not in ALLOWED])
def test_every_other_change_is_refused_and_leaves_the_row(start, target):
    row = NotificationFactory(status=start)
    assert apply_transition(row.pk, to_status=target) is None
    row.refresh_from_db(); assert row.status == start

@pytest.mark.parametrize("start,target", [("PENDING","FAILED"), ("SENT","DELIVERED"),
                                          ("SENT","FAILED"), ("FAILED","DELIVERED")])
def test_whatsapp_only_changes_are_refused_for_email(start, target): ...

def test_whatsapp_failure_creates_the_email_in_the_same_transaction():
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    apply_transition(row.pk, to_status="FAILED", error_code="131026")
    email = Notification.objects.get(fallback_of=row)
    assert email.channel == "EMAIL" and email.status == "PENDING"
    assert email.expires_at == row.expires_at and email.event == row.event
    assert email.application_id == row.application_id
    assert email.dues_request_id == row.dues_request_id

def test_email_failure_creates_no_further_row(): ...

def test_crash_while_creating_the_fallback_rolls_back_the_failure(monkeypatch):
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    monkeypatch.setattr(services, "_create_fallback", mock.Mock(side_effect=RuntimeError))
    with pytest.raises(RuntimeError):
        apply_transition(row.pk, to_status="FAILED", error_code="x")
    row.refresh_from_db(); assert row.status == "SENT"

def test_stale_reader_cannot_turn_delivered_into_failed():
    row = NotificationFactory(status="SENT")
    apply_transition(row.pk, to_status="DELIVERED")
    assert apply_transition(row.pk, to_status="FAILED", error_code="NO_DELIVERY_RECEIPT") is None
    assert not Notification.objects.filter(fallback_of=row).exists()

def test_late_delivered_keeps_the_email_already_created(): ...

def test_stale_send_result_does_not_overwrite_recovery():
    row = NotificationFactory(status="SENDING", attempts=1)
    apply_transition(row.pk, to_status="FAILED", error_code="SEND_INTERRUPTED")
    assert apply_transition(row.pk, to_status="SENT", expected_attempts=1) is None

def test_wrong_attempt_number_is_refused(): ...   # SENDING, attempts=2, expected_attempts=1

def test_leaving_sending_clears_sending_started_at(): ...  # to SENT, PENDING and FAILED
def test_claiming_increments_attempts_and_sets_started_at(): ...  # attempts_delta=1
def test_failed_and_expired_log_a_warning_with_allowlisted_fields_only(caplog):
    # message "notification_failed" / "notification_expired"; extras limited to
    # notification_id, event, channel, status, error_code

@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_webhook_and_job_race_make_one_email():
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    run_concurrently(lambda: apply_transition(row.pk, to_status="FAILED", error_code="a"),
                     lambda: apply_transition(row.pk, to_status="FAILED", error_code="b"))
    assert Notification.objects.filter(fallback_of=row).count() == 1
```

Import `run_concurrently` from `apps.applications.tests.test_reference_numbers`.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_transitions.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Implement `apply_transition` and `_create_fallback(parent, *, now)`**

Use `transaction.atomic()`, then `select_for_update().get(pk=...)`, then the table check, field changes, fallback and save. Field changes follow the spec section 4 table. `DELIVERED` sets `delivered_at`; leaving `SENDING` clears `sending_started_at`; entering `SENDING` sets it. `_create_fallback` runs `Notification.objects.get_or_create(fallback_of=parent, defaults=...)` in a nested `atomic()`. On `IntegrityError` it re-checks that the fallback exists and re-raises otherwise. Log after the atomic block.

- [ ] **Step 4: Run the tests**

Expected: PASS.

- [ ] **Step 5: Commit**: `feat: notification transition service with atomic fallback`

---

### Task 4: Enqueue, relevance and the 10 hooks

**Files:**
- Modify: `backend/apps/notifications/services.py`, `backend/apps/applications/services.py:177-193` and `:343-344`, `backend/apps/dues/services.py:129-138`, `:213-225`, `:254-260`
- Create: `backend/apps/notifications/tests/test_enqueue.py`, `tests/test_relevance.py`

**Interfaces:**
- Produces:
  - `enqueue(application, event: str, *, dues_request=None, created_by=None) -> Notification`
  - `still_relevant(row: Notification) -> bool`
  - `first_channel(doctor) -> str`

- [ ] **Step 1: Write the failing tests**

`test_enqueue.py`:

```python
def test_opted_in_doctor_with_valid_mobile_starts_on_whatsapp(): ...
def test_not_opted_in_starts_on_email(): ...
def test_opted_in_with_incomplete_phone_starts_on_email():  # Review Focus 3
    doctor = DoctorFactory(phone_number="0101", whatsapp_opt_in=True)
    assert first_channel(doctor) == "EMAIL"
def test_expires_at_is_72_hours_after_enqueue(): ...

# One test per event: a committed change leaves exactly one row, a rolled-back change none.
@pytest.mark.parametrize("event,action", EVENT_ACTIONS)  # all 10, via the real services
def test_committed_change_leaves_one_row(event, action): ...
@pytest.mark.parametrize("event,action", EVENT_ACTIONS)
def test_rolled_back_change_leaves_no_row(event, action):
    with pytest.raises(RuntimeError), transaction.atomic():
        action(); raise RuntimeError
    assert not Notification.objects.filter(event=event).exists()

def test_second_correction_on_one_application_sends_again(): ...
def test_under_review_sends_nothing(): ...
def test_setting_the_same_payment_status_again_sends_nothing(): ...
def test_receipt_upload_and_removal_send_nothing(): ...       # _change_payment_status has no hook
def test_dues_rows_carry_their_dues_request(): ...
```

`test_relevance.py`:

```python
@pytest.mark.parametrize("event,source_state,expected", [
    ("CORRECTION_NEEDED", {"status": "NEEDS_CORRECTION"}, True),
    ("CORRECTION_NEEDED", {"status": "SUBMITTED"}, False),
    ("PAYMENT_CONFIRMED", {"payment_status": "CONFIRMED"}, True),
    ("PAYMENT_CONFIRMED", {"payment_status": "REJECTED"}, False),
    ("PAYMENT_RECEIPT_REJECTED", {"payment_status": "REJECTED"}, True),
    ("PAYMENT_RECEIPT_REJECTED", {"payment_status": "PENDING_REVIEW"}, False),
    ("DUES_REQUESTED", {"dues_status": "REQUESTED"}, True),
    ("DUES_REQUESTED", {"dues_status": "PENDING_REVIEW"}, False),
    ("DUES_REQUESTED", {"dues_status": "CANCELLED"}, False),
    ("DUES_RECEIPT_REJECTED", {"dues_status": "REJECTED"}, True),
    ("DUES_RECEIPT_REJECTED", {"dues_status": "PENDING_REVIEW"}, False),
])
def test_still_relevant(event, source_state, expected): ...

@pytest.mark.parametrize("event", ["APPLICATION_RECEIVED", "APPROVED", "REJECTED",
                                   "DUES_CONFIRMED", "DUES_CANCELLED"])
def test_other_events_are_always_relevant(event): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_enqueue.py apps/notifications/tests/test_relevance.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `enqueue`, `first_channel`, `still_relevant`**

`enqueue` calls `transaction.get_connection().in_atomic_block` and raises `RuntimeError` when false, like `generate_reference_number`. It checks that `dues_request.application_id == application.pk`. `notifications.services` may import only models and `apps.applications.access` from those apps, never their `services`, to avoid an import cycle.

- [ ] **Step 4: Add the hooks**

| Location | Change |
|---|---|
| `applications.services.transition` | At the end of the `atomic` block, after both branches: `event = STATUS_EVENTS.get(to_status)`; if set, `enqueue(app, event)`. `STATUS_EVENTS` maps `SUBMITTED`, `NEEDS_CORRECTION`, `APPROVED`, `REJECTED` |
| `applications.services.set_payment_status` | Inside `if app.payment_status != status:`, enqueue for `CONFIRMED` and `REJECTED`. Never in `_change_payment_status` |
| `dues.services.create_dues_request` | `DUES_REQUESTED` |
| `dues.services.review_dues_receipt` | `DUES_CONFIRMED` or `DUES_RECEIPT_REJECTED` by decision |
| `dues.services.cancel_dues_request` | `DUES_CANCELLED` |

- [ ] **Step 5: Run the affected suites**

Run: `.venv/Scripts/python -m pytest apps/notifications apps/applications apps/dues -q`
Expected: PASS, including every existing test.

- [ ] **Step 6: Commit**: `feat: enqueue notifications on application, payment and dues changes`

---

### Task 5: Provider clients

**Files:**
- Create: `backend/apps/notifications/providers.py`, `tests/test_providers.py`

**Interfaces:**
- Produces:

```python
class ProviderError(Exception):      # .code: str; __init__(self, code: str)
class TemporaryProviderError(ProviderError): ...
class UnknownResultError(ProviderError): ...
class PermanentProviderError(ProviderError): ...

class WhatsAppClient:
    def send_template(self, *, to: str, template: str, parameters: list[str]) -> str: ...
    def send_text(self, *, to: str, body: str) -> str: ...      # timeout=(2, 3)
class EmailClient:
    def send(self, *, to: str, subject: str, html: str, text: str) -> str: ...
class FakeWhatsAppClient / FakeEmailClient:   # .sent: list[dict]; .errors: list[Exception]
def get_whatsapp_client() -> WhatsAppClient | FakeWhatsAppClient: ...
def get_email_client() -> EmailClient | FakeEmailClient: ...
```

- [ ] **Step 1: Write the failing tests** (mock `requests.post` and a stubbed SES client)

```python
def test_whatsapp_template_payload():
    # POST https://graph.facebook.com/{version}/{phone_id}/messages
    # json: messaging_product=whatsapp, to, type=template,
    # template={name, language={code:"ar"}, components=[{type:"body", parameters:[{type:"text", text}]}]}
    # timeout=(3, 7); bearer token header; returns messages[0].id

def test_whatsapp_400_is_permanent_with_metas_code(): ...      # .code == "131026"
def test_whatsapp_401_without_code_uses_http_status(): ...     # .code == "HTTP_401"
@pytest.mark.parametrize("status", [429, 500, 503])
def test_whatsapp_retryable_status_is_temporary(status): ...
def test_whatsapp_connection_refused_is_temporary(): ...       # code CONNECT_FAILED
def test_whatsapp_connect_timeout_is_temporary(): ...          # code CONNECT_FAILED
def test_whatsapp_read_timeout_is_unknown(): ...               # code UNKNOWN_RESULT
def test_whatsapp_connection_dropped_after_send_is_unknown(): ...
def test_whatsapp_200_without_an_id_is_unknown(): ...
def test_errors_carry_no_provider_text_or_chained_cause():
    # exc.__cause__ is None, exc.__suppress_context__ is True, and str(exc) equals the code
def test_send_text_uses_short_timeout(): ...                   # timeout=(2, 3)

def test_ses_client_config():
    # connect_timeout=3, read_timeout=7, retries total_max_attempts == 1
def test_ses_payload_is_utf8_html_and_text(): ...              # returns MessageId
def test_ses_message_rejected_is_permanent(): ...              # .code == "MessageRejected"
@pytest.mark.parametrize("code", ["TooManyRequestsException", "LimitExceededException",
                                  "SendingPausedException", "AccountSuspendedException"])
def test_ses_account_level_errors_are_temporary(code): ...
def test_ses_connect_error_is_temporary(): ...
def test_ses_read_timeout_is_unknown(): ...
def test_missing_credentials_are_temporary(): ...              # .code == "CREDENTIALS"
def test_settings_select_fakes_in_tests(): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_providers.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Implement the clients**

This classification decides between retrying and going to email:

```python
except requests.exceptions.ConnectionError as exc:
    # ConnectTimeout and refused connections never reached Meta; everything else
    # (aborted, reset, remote closed) may have, so it is treated as unknown.
    reason = getattr(exc.args[0], "reason", None) if exc.args else None
    if isinstance(exc, requests.exceptions.ConnectTimeout) or isinstance(
        reason, urllib3.exceptions.NewConnectionError
    ):
        raise TemporaryProviderError("CONNECT_FAILED") from None
    raise UnknownResultError("UNKNOWN_RESULT") from None
except requests.exceptions.Timeout:
    raise UnknownResultError("UNKNOWN_RESULT") from None
```

For SES, create one client with `boto3.client("sesv2", region_name=settings.SES_REGION, config=Config(connect_timeout=3, read_timeout=7, retries={"total_max_attempts": 1, "mode": "standard"}))` and reuse it, because clients are thread safe and expensive to build. Use `client.send_email(FromEmailAddress=..., Destination={"ToAddresses": [to]}, Content={"Simple": {...}})` with `Charset: "UTF-8"`. Credentials come from the default chain here; Task 14 replaces the session. Classify `EndpointConnectionError` and `ConnectTimeoutError` as temporary; `ReadTimeoutError` and `ConnectionClosedError` as unknown; `NoCredentialsError` and `CredentialRetrievalError` as temporary with code `CREDENTIALS`; `ClientError` by `response["Error"]["Code"]`, using the temporary list above plus any HTTP 5xx, otherwise permanent.

`get_*_client()` uses `lru_cache` and reads `NOTIFICATION_PROVIDERS`. Fakes return `fake-<uuid4>`, pop `.errors` when non-empty and raise, and record to `.sent`. Add an autouse fixture in `apps/notifications/tests/conftest.py` that clears the fakes between tests.

- [ ] **Step 4: Run the tests**

Expected: PASS.

- [ ] **Step 5: Commit**: `feat: WhatsApp and SES clients with explicit error classes`

---

### Task 6: Claiming and recording outcomes

**Files:**
- Modify: `backend/apps/notifications/services.py`
- Create: `backend/apps/notifications/tests/test_claim.py`

**Interfaces:**
- Consumes: `apply_transition`, `still_relevant`, `Notification`.
- Produces:

```python
@dataclass(frozen=True)
class Claim:
    notification_id: UUID
    attempts: int
    channel: str
    event: str
    reference_number: str
    amount: Decimal | None
    recipient: str = field(repr=False)   # full address, in memory only, never logged
    recipient_masked: str

def claim_next(channel: str, *, now: datetime) -> Claim | None: ...
def record_accepted(claim: Claim, *, provider_message_id: str) -> None: ...
def record_temporary(claim: Claim, *, error_code: str, now: datetime) -> None: ...
def record_unknown(claim: Claim, *, now: datetime) -> None: ...
def record_permanent(claim: Claim, *, error_code: str) -> None: ...
```

- [ ] **Step 1: Write the failing tests**

```python
def test_claim_sets_sending_and_increments_attempts(): ...
def test_claim_skips_rows_not_yet_due(): ...
def test_claim_takes_oldest_first(): ...
def test_claim_reads_the_current_phone_not_the_one_at_enqueue(): ...

# Each check runs at claim, uses no attempt, and moves on to the next due row.
def test_past_expiry_becomes_expired(): ...
def test_irrelevant_row_becomes_superseded_with_no_fallback(): ...
def test_allowlist_mode_suppresses_unlisted_recipient_with_no_fallback(settings): ...
@pytest.mark.parametrize("channel", ["WHATSAPP", "EMAIL"])
def test_allowlist_applies_to_each_channel(settings, channel): ...
def test_allowlist_applies_to_a_fallback_email(settings): ...
def test_opt_in_withdrawn_fails_with_opted_out_and_creates_email():
    row = NotificationFactory(channel="WHATSAPP", application__doctor__whatsapp_opt_in=False)
    assert claim_next("WHATSAPP", now=timezone.now()) is None
    row.refresh_from_db()
    assert (row.status, row.error_code, row.attempts) == ("FAILED", "OPTED_OUT", 0)
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()
def test_invalid_phone_at_claim_is_opted_out(): ...
def test_fallback_email_of_an_obsolete_message_is_superseded():
    # DUES_REQUESTED WhatsApp row fails, the request is cancelled, the email row claims as SUPERSEDED

def test_temporary_error_retries_after_5_then_15_minutes(): ...
def test_third_temporary_error_fails_and_creates_email(): ...
def test_unknown_result_on_whatsapp_goes_to_email_at_once():
    # status FAILED, error_code UNKNOWN_RESULT, one attempt used
def test_unknown_result_on_email_retries_then_fails_with_no_fallback(): ...
def test_permanent_error_on_email_fails_with_no_fallback(): ...
def test_claim_repr_hides_the_recipient():
    assert "01012345678" not in repr(claim)

@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_safety_two_workers_on_one_row_make_one_claim():
    row = NotificationFactory()
    a, b = run_concurrently(lambda: claim_next("WHATSAPP", now=NOW),
                            lambda: claim_next("WHATSAPP", now=NOW))
    assert sum(c is not None for c in (a, b)) == 1

@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_progress_a_locked_row_does_not_block_another():
    # Hold row A with select_for_update in a thread until an Event is set.
    # claim_next must return row B, measured under 2 seconds, while A is still locked.
```

Removing the locking and status check must fail the safety test. Removing only `skip_locked` must fail the progress test. Verify both by temporarily editing the code during Step 4, and revert.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_claim.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`claim_next` loops. Each pass opens a short transaction with `select_for_update(skip_locked=True, of=("self",))`, filtered by `status=PENDING`, the channel and `next_attempt_at__lte=now`, ordered by `next_attempt_at, created_at`. Then it applies, in order: expiry, relevance, allowlist, consent (WhatsApp only: `whatsapp_opt_in` and `normalize_mobile`). A row failing a check goes through `apply_transition` and the loop continues. A passing row becomes `SENDING` with `attempts_delta=1` and returns a `Claim`. An email row with a blank address is still claimed; the sender reports `NO_ADDRESS`. Constants: `MAX_ATTEMPTS = 3`, `RETRY_DELAYS = {1: timedelta(minutes=5), 2: timedelta(minutes=15)}`. Every `record_*` passes `expected_attempts=claim.attempts` and `claim.recipient_masked`.

- [ ] **Step 4: Run the tests and the two mutation checks**

Expected: PASS, and each mutation fails its own test.

- [ ] **Step 5: Commit**: `feat: claim notifications with relevance, allowlist and consent checks`

---

### Task 7: The job loop and command

**Files:**
- Create: `backend/apps/notifications/sender.py`, `management/__init__.py`, `management/commands/__init__.py`, `management/commands/send_notifications.py`, `tests/test_sender.py`
- Modify: `backend/apps/notifications/services.py`, `backend/entrypoint.sh`

**Interfaces:**
- Consumes: `claim_next`, `record_*`, `get_whatsapp_client`, `get_email_client`, `render_email`, `template_parameters`, `to_e164`.
- Produces:
  - `services.expire_overdue(*, now, limit=500) -> int`
  - `services.recover_stuck(*, now, limit=500) -> int`
  - `services.apply_delivery_timeout(*, now, limit=500) -> int`
  - `services.oldest_due_age_seconds(*, now) -> int | None`
  - `sender.run_once(*, now=None, clock=time.monotonic) -> RunSummary`

- [ ] **Step 1: Write the failing tests**

```python
def test_order_of_a_run_expire_recover_timeout_send(): ...
def test_off_mode_only_expires_and_summarises(settings):
    settings.NOTIFICATIONS_MODE = "off"
    # stale PENDING -> EXPIRED; stuck SENDING and old SENT untouched; nothing sent; summary logged

def test_stuck_whatsapp_after_10_minutes_fails_with_send_interrupted_and_email(): ...
def test_stuck_email_fails_with_no_fallback(): ...
def test_row_sending_for_9_minutes_is_left_alone(): ...
def test_sent_whatsapp_after_30_minutes_fails_with_no_delivery_receipt(): ...
def test_sent_email_is_never_timed_out(): ...
def test_sweeps_stop_at_500_rows(): ...

def test_email_rows_are_sent_before_whatsapp(): ...
def test_at_most_200_rows_per_run(): ...
def test_stops_claiming_with_under_15_seconds_left():
    # fake clock: after one send only 14 of 240 seconds remain; the rest stay PENDING, attempts 0

def test_five_consecutive_errors_skip_that_provider_only():
    whatsapp.errors = [TemporaryProviderError("HTTP_500")] * 5
    # 8 WhatsApp rows + 2 email rows due:
    # 5 attempted, 3 still attempts=0 PENDING; both emails sent
def test_unknown_results_count_towards_the_streak(): ...
def test_a_success_resets_the_streak(): ...
def test_each_attempt_is_one_row_in_the_database(): ...

def test_whatsapp_send_uses_e164_template_and_parameters(): ...
def test_email_row_without_address_fails_visibly(user_with_no_email):   # Review Focus 1
    # status FAILED, error_code NO_ADDRESS; provider not called; run continues with the next row
def test_a_row_that_raises_unexpectedly_does_not_stop_the_run():
    # render raises for one row: it ends FAILED with SEND_ERROR, and the next row still sends

def test_summary_logs_counts_and_oldest_age_only(caplog):
    # message "notify_run"; extra has oldest_due_age_seconds and integer counts
def test_no_phone_address_or_message_text_in_any_log(caplog): ...

def test_command_logs_notify_run_failed_and_reraises(monkeypatch, caplog): ...
def test_command_flushes_telemetry_on_exit(monkeypatch): ...
def test_overlapping_runs_send_one_row_once(): ...  # transaction=True, run_concurrently(run_once, run_once)

def test_cancelled_dues_never_send_the_payment_request():
    # Create dues; the first send raises TemporaryProviderError; cancel; advance past the retry.
    # Across WhatsApp and any fallback email, no sent message uses med_dues_requested again.
def test_rows_held_through_off_mode_pass_the_relevance_check_on_resuming(settings): ...
def test_fallback_created_after_expiry_is_expired_on_the_next_run(): ...
def test_two_dues_requests_each_name_their_own_amount_on_both_channels():
    # Requests of 1000 and 2500: cancelling the first sends only "1٬000 ج.م", and the wording
    # contains neither the second amount nor any claim that nothing is owed.
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_sender.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Implement the sweeps and `run_once`**

Constants: `MAX_ROWS = 200`, `BUDGET_SECONDS = 240`, `MIN_REMAINING_SECONDS = 15`, `OUTAGE_STREAK = 5`, `STUCK_AFTER = timedelta(minutes=10)`. `RunSummary` is a dataclass of integer counts plus `oldest_due_age_seconds`. Go through `EMAIL` and then `WHATSAPP`; a channel's streak of temporary or unknown errors ends that channel for this run, and a success resets it. `ProviderError` subclasses map to `record_*`. Any other exception maps to `record_permanent(error_code="SEND_ERROR")` and is logged by notification ID only with no traceback, because a traceback could hold a recipient.

- [ ] **Step 4: Implement the command and entrypoint mode**

`handle()` calls `run_once()`. On a fatal exception it logs `notify_run_failed` at `ERROR` and re-raises; a `finally` block calls `_flush_telemetry()`, which does `get_logger_provider().force_flush()` when the provider has that method. Add this case to `entrypoint.sh`, and document it in the header comment:

```sh
    notify)
        exec python manage.py send_notifications
        ;;
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest apps/notifications -q`
Expected: PASS.

- [ ] **Step 6: Commit**: `feat: send_notifications job with budget and outage handling`

---

### Task 8: Telemetry and log masking

**Files:**
- Modify: `backend/manage.py`, `backend/config/logging.py`, `backend/config/tests/test_logging.py`, `backend/config/telemetry.py` (docstring only)
- Create: `backend/config/tests/test_manage.py`, `backend/apps/notifications/tests/test_privacy.py`

**Interfaces:**
- Produces: `manage._starts_telemetry(argv: list[str]) -> bool`; `mask_digit_runs` keeps its name and now also masks emails and spaced phones, so `config/telemetry.py` needs no code change.

- [ ] **Step 1: Write the failing tests**

```python
# config/tests/test_manage.py
def test_send_notifications_starts_telemetry_before_django(monkeypatch):
    calls = []
    monkeypatch.setattr("config.telemetry.configure_telemetry", lambda: calls.append("telemetry"))
    monkeypatch.setattr("django.core.management.execute_from_command_line",
                        lambda argv: calls.append("django"))
    monkeypatch.setattr(sys, "argv", ["manage.py", "send_notifications"])
    manage.main()
    assert calls == ["telemetry", "django"]

def test_other_commands_do_not_start_telemetry(monkeypatch): ...
```

```python
# config/tests/test_logging.py: replace test_shorter_numbers_are_untouched, whose phone is now masked
def test_ordinary_numbers_are_untouched():
    assert mask_digit_runs("year 2026, total 3025") == "year 2026, total 3025"
def test_dates_and_uuids_are_untouched():
    text = "2026-11-02 10:30:15 8f14e45f-ceea-467f-a0f2-1a2b3c4d5e6f"
    assert mask_digit_runs(text) == text
@pytest.mark.parametrize("phone", ["01012345678", "201012345678", "+201012345678",
                                   "010 1234 5678", "010-1234-5678", "٠١٠١٢٣٤٥٦٧٨"])
def test_phones_are_masked(phone):
    assert phone not in mask_digit_runs(f"to {phone}")
def test_emails_are_masked():
    assert "ahmed@example.com" not in mask_digit_runs("to ahmed@example.com")
```

```python
# apps/notifications/tests/test_privacy.py
@pytest.mark.parametrize("secret", ["ahmed@example.test", "010 1234 5678", "+201012345678",
                                    "٠١٠١٢٣٤٥٦٧٨", "نص الرسالة"])
def test_seeded_values_never_reach_logs(caplog, secret):
    # A fake client raises an error built around `secret`; run_once; `secret` is in no record,
    # including exc_text and extra fields; notification ID and error code are present.
def test_span_and_log_attributes_are_masked(): ...  # uses MaskingLogRecordProcessor / MaskingSpanProcessor
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest config/tests apps/notifications/tests/test_privacy.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `manage.py`, before importing Django's command runner:

```python
if _starts_telemetry(sys.argv):
    from config.telemetry import configure_telemetry

    configure_telemetry()
```

The comment states why: `TelemetryLogHandler` binds its provider when Django builds logging, so calling this inside the command is too late.

In `config/logging.py`, change `_DIGIT_RUN` to `\d{11,}`, and add `_EMAIL = re.compile(r"[^\s@\"']+@[^\s@\"']+")` and a mobile pattern matching the Egyptian shape with optional separators: `(?:\+?20|0)1[0125](?:[\s-]?\d){8}`. Mask the separated form before the digit run. Update the module docstring, which still says "14+".

- [ ] **Step 4: Run the whole backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS. Fix any existing test that relied on a phone or email surviving in a log.

- [ ] **Step 5: Commit**: `feat: start telemetry for send_notifications and widen log masking`

---

### Task 9: Opt-in service and API

**Files:**
- Modify: `backend/apps/doctors/services.py`, `backend/apps/doctors/api/urls.py`, `views.py`, `serializers.py`, `backend/apps/doctors/tests/test_api.py`
- Create: `backend/apps/doctors/tests/test_whatsapp_opt_in.py`

**Interfaces:**
- Produces:
  - `set_whatsapp_opt_in(doctor, *, enabled: bool, actor, request=None) -> Doctor`
  - `GET/PUT /api/v1/profile/notifications/` returning `{doctor_id, whatsapp_opt_in, whatsapp_opt_in_at, phone_number, phone_valid}`; PUT body `{whatsapp_opt_in: bool}`

- [ ] **Step 1: Write the failing tests**

```python
def test_opt_in_sets_flag_time_and_audit():
    # audit WHATSAPP_OPT_IN_CHANGED, metadata {"enabled": True, "source": "profile"},
    # and the metadata has no phone number
def test_opt_out_clears_flag_and_time(): ...
def test_repeating_the_same_value_writes_no_audit(): ...
def test_opt_in_refused_for_incomplete_phone():             # Review Focus 3
    doctor = DoctorFactory(phone_number="0101")
    with pytest.raises(ValidationFailed):
        set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
def test_opt_in_works_on_a_frozen_profile():
    # application UNDER_REVIEW: update_profile raises ApplicationNotEditable, opt-in still works
def test_another_user_cannot_change_it(): ...               # PermissionDeniedError

def test_changing_the_phone_clears_the_opt_in_and_audits(): ...
def test_same_number_in_another_form_keeps_the_opt_in():
    # "+201012345678" normalizes to the stored 01012345678
def test_saving_other_profile_fields_keeps_the_opt_in(): ...
def test_serializer_cannot_set_opt_in_through_profile_patch(): ...

def test_get_returns_own_state_and_doctor_id(): ...
def test_put_requires_authentication_and_doctor_role(): ...
def test_put_rejects_non_boolean(): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/doctors -q`
Expected: new tests FAIL.

- [ ] **Step 3: Implement**

`set_whatsapp_opt_in` uses `@transaction.atomic`, locks the row with `select_for_update`, and never calls `ensure_profile_editable`. Error field `whatsapp_opt_in`, message `رقم الهاتف المحمول غير صحيح`. In `update_profile`, read `normalize_mobile(doctor.phone_number)` before the `setattr` loop. If the opt-in is on and the normalized number changed, clear it and audit it. Keep the view thin, following `ProfileView`, with `permission_classes = [IsDoctor]`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest apps/doctors apps/audit -q`
Expected: PASS.

- [ ] **Step 5: Commit**: `feat: WhatsApp opt-in endpoint, cleared when the phone changes`

---

### Task 10: Webhook: handshake, signature, statuses

**Files:**
- Create: `backend/apps/notifications/webhook.py`, `api/__init__.py`, `api/urls.py`, `api/views.py`, `tests/test_webhook.py`
- Modify: `backend/config/api/urls.py`

**Interfaces:**
- Consumes: `apply_transition`.
- Produces:
  - `verify_signature(raw_body: bytes, header: str | None) -> bool`
  - `process_webhook(raw_body: bytes, signature_header: str | None) -> None`, raising `InvalidSignature`
  - `verify_subscription(params) -> str | None`, the challenge or `None`
  - URL name `whatsapp-webhook`; path `notifications/whatsapp/webhook/`

- [ ] **Step 1: Write the failing tests**, posting raw bytes with `client.generic("POST", URL, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sign(body))` and no authentication

```python
def test_handshake_returns_challenge(): ...             # hub.mode=subscribe, right token -> 200, challenge
def test_handshake_wrong_token_is_403(): ...
def test_handshake_wrong_mode_is_403(): ...
def test_bad_signature_is_403_and_changes_nothing(): ...
def test_missing_signature_is_403(): ...
def test_empty_app_secret_refuses_everything(settings): ...   # fail closed
def test_signature_covers_the_raw_bytes():
    # The same JSON re-serialized with different spacing fails under the first signature.

@pytest.mark.parametrize("start,webhook_status,expected", [
    ("SENT", "sent", "SENT"), ("SENT", "delivered", "DELIVERED"), ("SENT", "read", "DELIVERED"),
    ("SENT", "failed", "FAILED"),
    ("DELIVERED", "sent", "DELIVERED"), ("DELIVERED", "delivered", "DELIVERED"),
    ("DELIVERED", "read", "DELIVERED"), ("DELIVERED", "failed", "DELIVERED"),
    ("FAILED", "sent", "FAILED"), ("FAILED", "delivered", "DELIVERED"),
    ("FAILED", "read", "DELIVERED"), ("FAILED", "failed", "FAILED"),
])
def test_status_table(start, webhook_status, expected): ...    # spec section 7

def test_failed_records_metas_code_and_creates_email(): ...    # errors[0].code -> "131026"
def test_repeating_a_failed_status_creates_one_email(): ...
def test_webhook_only_finds_whatsapp_rows(): ...               # same ID on an EMAIL row is untouched
def test_other_phone_number_id_is_ignored(): ...

@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"entry": "x"}',
                                  b'{"entry": [{"changes": [{"value": {"statuses": ["x"]}}]}]}'])
def test_signed_but_malformed_body_returns_200_and_changes_nothing(body): ...  # Review Focus 2

def test_batch_with_known_unknown_and_repeated_ids_handles_each():             # Review Focus 5
    # delivered(known), delivered(unknown), failed(known2), failed(known2) -> 200; both rows updated

def test_database_failure_returns_500_so_meta_retries(monkeypatch):
    # apply_transition raises OperationalError -> 500 and no 200 acknowledgement
def test_payload_is_never_logged(caplog): ...
def test_webhook_needs_no_session_and_no_csrf(): ...           # enforce_csrf_checks=True client
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_webhook.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`verify_signature` compares `"sha256=" + hmac_sha256_hex` with `hmac.compare_digest`, and returns `False` when the secret is blank. Parse with `json.loads` only after verification, and walk `entry[].changes[].value` defensively with type checks, because Task 11 adds `messages` here.

The view sets `authentication_classes = []`, `permission_classes = []`, `throttle_classes = []` and `@extend_schema(exclude=True)` so the OpenAPI schema stays warning-free. Read `request.body` before touching `request.data`. `HttpResponse(challenge, content_type="text/plain")` for the handshake; an empty 200 for a POST. Let database errors propagate.

- [ ] **Step 4: Run the tests**

Expected: PASS.

- [ ] **Step 5: Commit**: `feat: signed WhatsApp webhook applying delivery statuses`

---

### Task 11: Stop and help replies

**Files:**
- Create: `backend/apps/notifications/inbound.py`, `tests/test_inbound.py`
- Modify: `backend/apps/notifications/webhook.py`, `backend/apps/doctors/services.py`

**Interfaces:**
- Consumes: `process_webhook`, `from_whatsapp_sender`, `to_e164`, `STOP_CONFIRMATION`, `HELP_REPLY`, `WhatsAppClient.send_text`.
- Produces:
  - `doctors.services.stop_whatsapp_for_number(local: str, *, message_time: datetime) -> bool`
  - `doctors.services.claim_help_reply(local: str, *, now: datetime) -> bool`
  - `inbound.is_stop_word(text: str) -> bool`
  - `inbound.Reply`, a frozen dataclass with `to: str` (repr hidden) and `body: str`
  - `inbound.handle_message(message: dict, *, now: datetime) -> Reply | None`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("text", ["إيقاف", "ايقاف", " إيقاف. ", "stop", "STOP", "Stop!", "إيقاف،"])
def test_stop_words(text): assert is_stop_word(text)

@pytest.mark.parametrize("text", ["please stop texting me", "لا تقم بإيقاف الطلب", "", "stopp"])
def test_not_stop_words(text): assert not is_stop_word(text)

def test_stop_clears_opt_in_audits_as_system_and_confirms():
    # whatsapp_opt_in False; AuditLog user None, metadata {"enabled": False, "source": "whatsapp_reply"};
    # send_text called once with STOP_CONFIRMATION
def test_two_doctors_sharing_a_number_are_both_stopped(): ...
def test_repeated_stop_changes_nothing_and_sends_no_second_reply(): ...
def test_old_stop_cannot_undo_a_newer_opt_in():
    # message timestamp earlier than whatsapp_opt_in_at: flag stays True, no reply
def test_pending_row_goes_to_email_after_a_stop(): ...
def test_stop_works_in_off_mode_without_a_reply(settings): ...
def test_allowlist_mode_replies_only_to_listed_numbers(settings): ...

def test_other_text_gets_help_once_in_24_hours(): ...          # second within 24h: no reply; after: reply
def test_non_text_message_gets_help_not_stop(): ...
def test_sentence_containing_stop_gets_help(): ...
def test_unknown_number_gets_no_action_and_no_reply(): ...
def test_incomplete_profile_number_never_matches():            # Review Focus 3
    # doctor with phone "0101"; sender 201012345678: unchanged, no reply
def test_non_egyptian_sender_is_ignored(): ...
def test_malformed_timestamp_is_treated_as_now(): ...

def test_failed_reply_still_returns_200_and_keeps_the_stop():
    # send_text raises each ProviderError class
def test_at_most_one_reply_per_request(): ...
def test_reply_is_sent_after_commit():
    # with django_capture_on_commit_callbacks or by asserting the stop is visible in send_text
def test_message_text_is_never_logged_or_stored(caplog): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_inbound.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`is_stop_word` applies `normalize_arabic_name`, strips ASCII and Arabic punctuation (`،؛؟!.…`), casefolds, and tests membership in `{"ايقاف", "stop"}`.

`stop_whatsapp_for_number` locks matching doctors with `Doctor.objects.select_for_update().filter(phone_number=local).order_by("pk")`, skips those with `whatsapp_opt_in_at > message_time`, and audits each change with `actor=None`. `claim_help_reply` returns `True` if any matching doctor's `whatsapp_help_sent_at` is null or over 24 hours old, and updates all of them.

`process_webhook` collects `Reply` objects, then sends the first one outside the transaction under the mode rules. Catch `ProviderError` only and log its code.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest apps/notifications apps/doctors -q`
Expected: PASS.

- [ ] **Step 5: Commit**: `feat: honour WhatsApp stop replies and answer other messages once a day`

---

### Task 12: Admin history and resend

**Files:**
- Modify: `backend/apps/notifications/services.py`, `backend/apps/notifications/api/views.py`, `api/urls.py`, `backend/apps/common/exceptions.py`, `backend/apps/applications/api/admin_urls.py`, `backend/openapi.yaml`
- Create: `backend/apps/notifications/api/serializers.py`, `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `enqueue`, `still_relevant`, `lock_application`, `reviewable_applications`.
- Produces:
  - `services.resend(notification: Notification, *, actor, request=None) -> Notification`
  - `NotificationConflict` and `NotificationNotRelevant`, both 409
  - `GET /api/v1/admin/applications/{id}/notifications/`
  - `POST /api/v1/admin/applications/{id}/notifications/{nid}/resend/`, returning 201 with the new row

- [ ] **Step 1: Write the failing tests**

```python
def test_history_lists_newest_first_with_safe_fields_only():
    # keys exactly: id, event, channel, status, recipient_masked, error_code, attempts,
    # fallback_of, created_by_email, created_at, sent_at, delivered_at
def test_history_never_exposes_provider_message_id(): ...
def test_doctor_cannot_read_or_resend(): ...                   # 403
def test_anonymous_is_refused(): ...
def test_foreign_application_is_404(): ...
def test_draft_application_is_404(): ...

def test_notification_of_another_application_is_404(): ...     # Review Focus 4

def test_resend_creates_a_row_with_new_expiry_creator_and_audit():
    # created_by=admin; expires_at ~ now+72h; AuditLog NOTIFICATION_RESENT, metadata holds IDs only
def test_resend_reruns_routing(): ...                          # doctor opted out since: goes to EMAIL
@pytest.mark.parametrize("blocking", ["PENDING", "SENDING"])
def test_resend_conflicts_with_an_active_row(blocking): ...    # 409 NOTIFICATION_CONFLICT
def test_resend_conflicts_with_whatsapp_sent_inside_the_timeout(): ...
def test_resend_allowed_after_the_timeout(): ...
def test_resend_allowed_for_delivered_rows(): ...
def test_dues_requests_do_not_block_each_other():
    # pending DUES_REQUESTED for request B does not block resending failed request A
def test_resend_of_obsolete_action_is_409_not_relevant(): ...  # NOTIFICATION_NOT_RELEVANT
def test_resend_is_throttled_per_admin(settings): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_admin_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`resend` is `@transaction.atomic`: `lock_application`, relevance check, conflict query, `enqueue(..., created_by=actor)`, audit. Arabic messages: `يوجد إرسال قيد التنفيذ لهذا الإشعار` and `لم يعد هذا الإشعار مطلوبًا`. Views use `permission_classes = [IsAdmin]`; the resend view adds `ScopedRateThrottle` with `throttle_scope = "notification_resend"`. Export `admin_urlpatterns` from `apps/notifications/api/urls.py` and add them in `admin_urls.py` before `*router.urls`, as dues does. The history view sets `pagination_class = None`, because one application has few rows.

- [ ] **Step 4: Regenerate the schema and run the tests**

Run: `.venv/Scripts/python manage.py spectacular --file openapi.yaml --validate --fail-on-warn && .venv/Scripts/python -m pytest apps/notifications -q`
Expected: no warnings; PASS.

- [ ] **Step 5: Commit**: `feat: admin notification history and resend`

---

### Task 13: Production startup refusals

**Files:**
- Modify: `backend/config/settings/production.py`, `backend/config/tests/test_production_settings.py`

- [ ] **Step 1: Write the failing tests** using the existing `load_production(monkeypatch, ...)`

```python
def test_notifications_default_to_off(monkeypatch): ...         # loads with no provider settings
def test_unknown_mode_is_refused(monkeypatch): ...              # NOTIFICATIONS_MODE="on"
def test_unknown_providers_value_is_refused(monkeypatch): ...
def test_live_mode_refuses_fake_providers(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="NOTIFICATION_PROVIDERS"):
        load_production(monkeypatch, NOTIFICATIONS_MODE="live", NOTIFICATION_PROVIDERS="fake", **ALL)
@pytest.mark.parametrize("mode", ["allowlist", "live"])
@pytest.mark.parametrize("missing", ["WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_API_VERSION",
    "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "SES_REGION",
    "SES_FROM_ADDRESS", "NOTIFICATION_BASE_URL"])
def test_real_providers_need_every_setting(monkeypatch, mode, missing): ...
def test_allowlist_mode_needs_a_list(monkeypatch): ...
def test_live_with_real_providers_loads(monkeypatch): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest config/tests/test_production_settings.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add a block after the OCR block, in the same style, using `_require`. These checks only prove settings exist; SES production access is a phase 1 and phase 4 owner gate, because a startup check must not call a provider.

- [ ] **Step 4: Run the tests**

Expected: PASS.

- [ ] **Step 5: Commit**: `feat: refuse unsafe notification settings in production`

---

### Task 14: AWS credentials from the Azure identity

**Gate: do not start until the owner confirms phase 0b succeeded and gives its recorded audience, issuer and role. If phase 0b fails, skip this task: the default credential chain from Task 5 reads an access key from Key Vault references.**

**Files:**
- Create: `backend/apps/notifications/aws_auth.py`, `tests/test_aws_auth.py`
- Modify: `backend/apps/notifications/providers.py`

**Interfaces:**
- Consumes: `config.azure.get_azure_credential`.
- Produces: `ses_session() -> boto3.Session`, used by `EmailClient` in place of the bare `boto3.client`.

- [ ] **Step 1: Write the failing tests**

```python
def test_without_a_role_uses_the_default_chain(settings): ...
def test_with_a_role_exchanges_the_azure_token(settings):
    # get_token called with f"{AWS_WEB_IDENTITY_AUDIENCE}/.default";
    # assume_role_with_web_identity called with RoleArn, WebIdentityToken, a RoleSessionName
def test_credentials_refresh_before_expiry(): ...
def test_sts_client_uses_bounded_timeouts_and_one_attempt(): ...
def test_token_failure_becomes_temporary_credentials_error(): ...   # code CREDENTIALS
def test_token_is_never_logged(caplog): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest apps/notifications/tests/test_aws_auth.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Use `botocore.credentials.RefreshableCredentials.create_from_metadata` with a refresh function that gets the Azure token and calls STS, attach it to a `botocore.session.get_session()`, and wrap it in `boto3.Session(botocore_session=...)`. Adjust to whatever phase 0b recorded.

- [ ] **Step 4: Run the tests**

Expected: PASS. Report federation as verified only to the extent phase 0b proved it.

- [ ] **Step 5: Commit**: `feat: AWS credentials through the Azure managed identity`

---

### Task 15: Admin notifications panel

**Files:**
- Create: `frontend/src/features/admin/NotificationsPanel.tsx`, `NotificationsPanel.test.tsx`
- Modify: `frontend/src/api/schema.d.ts` (generated), `frontend/src/api/types.ts`, `frontend/src/api/keys.ts`, `frontend/src/api/endpoints/admin.ts`, `frontend/src/features/admin/queries.ts`, `frontend/src/pages/admin/AdminApplicationDetailPage.tsx`, `frontend/src/i18n/ar.ts`, `frontend/src/test/fixtures.ts`

**Interfaces:**
- Consumes: the Task 12 endpoints; reference-data `notificationEvents`, `notificationChannels`, `notificationStatuses`; `ActionDialog`; `choiceLabel`.
- Produces: `fetchNotifications(id)`, `resendNotification(id, nid)`, `useNotifications(id)`, `useResendNotification(id)`, `queryKeys.admin.notifications(id)`; `<NotificationsPanel applicationId reference />`.

- [ ] **Step 1: Regenerate the API types**

Run: `npm run gen:api`
Expected: `schema.d.ts` gains the notification paths.

- [ ] **Step 2: Write the failing tests**

```tsx
it("shows event, channel, status, time, and the masked recipient in an LTR span");
it("marks FAILED and EXPIRED rows prominently");
it("shows SUPERSEDED quietly as no longer needed");
it("labels a SENT email as accepted, delivery not confirmed, never delivered", () => {
  // expects text "قبله مزوّد البريد، والتسليم غير مؤكد"
});
it("labels a SENT WhatsApp row as sent, awaiting delivery");
it("explains known error codes in Arabic and uses a generic line for unknown ones");
it("resends only after confirming in the dialog");
it("shows the server message on a 409 and keeps the row list");
it("refreshes the list after a resend");
it("shows the empty state when there are no rows");
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npx vitest run src/features/admin/NotificationsPanel.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Implement**

Follow `DuesPanel.tsx`. Mount the panel directly after `DuesPanel` in `AdminApplicationDetailPage`. In `useDetailUpdate`, also invalidate `keys.notifications(id)`, because review actions create rows. Add `ar.admin.notifications`:

```ts
notifications: {
  title: "الإشعارات",
  empty: "لا توجد إشعارات لهذا الطلب بعد.",
  resend: "إعادة الإرسال",
  resendTitle: "إعادة إرسال الإشعار",
  resendConfirm: "سيُرسل هذا الإشعار إلى العضو مرة أخرى. هل تريد المتابعة؟",
  emailAccepted: "قبله مزوّد البريد، والتسليم غير مؤكد",
  whatsappSent: "أُرسل، بانتظار تأكيد التسليم",
  errors: {
    OPTED_OUT: "لم يفعّل العضو رسائل واتساب، فأُرسل بالبريد.",
    NO_DELIVERY_RECEIPT: "لم يصل تأكيد التسليم خلال المهلة، فأُرسل بالبريد.",
    UNKNOWN_RESULT: "نتيجة الإرسال غير معروفة، فأُرسل بالبريد.",
    SEND_INTERRUPTED: "توقف الإرسال قبل اكتماله.",
    CONNECT_FAILED: "تعذر الاتصال بمزود الخدمة.",
    NO_ADDRESS: "لا يوجد بريد إلكتروني مسجل للعضو.",
    SEND_ERROR: "حدث خطأ أثناء الإرسال.",
    generic: "رفض مزود الخدمة الرسالة (الرمز: {code}).",
  },
},
```

- [ ] **Step 5: Verify**

Run: `npx vitest run src/features/admin && npm run typecheck && npm run lint && npm run rtl:check`
Expected: all pass.

- [ ] **Step 6: Commit**: `feat: notifications panel on the admin application page`

---

### Task 16: Doctor opt-in on the profile and status pages

**Files:**
- Create: `frontend/src/features/notifications/useWhatsAppOptIn.ts`, `WhatsAppOptIn.tsx`, `WhatsAppPrompt.tsx`, `WhatsAppOptIn.test.tsx`, `WhatsAppPrompt.test.tsx`
- Modify: `frontend/src/api/endpoints/profile.ts`, `frontend/src/api/keys.ts`, `frontend/src/pages/doctor/ProfilePage.tsx`, `frontend/src/pages/application/StatusPage.tsx`, `frontend/src/i18n/ar.ts`, `frontend/src/test/fixtures.ts`

**Interfaces:**
- Consumes: `GET/PUT /api/v1/profile/notifications/`.
- Produces: `useWhatsAppOptIn()`, `useSetWhatsAppOptIn()`, `queryKeys.whatsappOptIn`; `<WhatsAppOptIn />`, `<WhatsAppPrompt />`.

- [ ] **Step 1: Write the failing tests**

```tsx
// WhatsAppOptIn
it("shows the number the consent applies to, in an LTR element");
it("saves on change and shows the new state");
it("stays usable when the profile is frozen");
it("disables the box and explains when the mobile number is invalid");
it("shows the server error when saving fails");
it("refetches after a profile save, because a new phone clears consent");

// WhatsAppPrompt
it("shows for a doctor not opted in, with a link to /profile");
it("does not show for a doctor already opted in");
it("hides after dismissal and stays hidden on the next render");
it("uses a storage key containing the doctor ID, so another doctor still sees it", () => {
  // dismiss as doctor A, render as doctor B: visible
});
it("still renders when localStorage throws");
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run src/features/notifications`
Expected: FAIL.

- [ ] **Step 3: Implement**

Copy the checkbox markup from `ReviewPage.tsx:146`. Wrap every `localStorage` access in `try/catch`. The key is `whatsapp-prompt-dismissed:<doctorId>`. Render `<WhatsAppOptIn />` in `ProfilePage` after `<ContactForm />`, and have `ContactForm`'s success path invalidate `queryKeys.whatsappOptIn`. Render `<WhatsAppPrompt />` in `StatusPage` directly after `<OutstandingDues />`. The paper-form replica is untouched.

Strings:

```ts
// ar.profile.whatsapp
title: "إشعارات واتساب",
consent: "أوافق على استلام إشعارات طلبي عبر واتساب على الرقم:",
hint: "يمكنك إيقافها في أي وقت من هنا أو بإرسال «إيقاف» ردًا على أي رسالة. وتصلك الإشعارات على بريدك الإلكتروني إذا لم تفعّلها.",
invalidPhone: "يرجى إدخال رقم هاتف محمول صحيح أولًا.",
// ar.status.whatsappPrompt
message: "فعّل إشعارات واتساب لمتابعة طلبك أولًا بأول.",
action: "تفعيل",
dismiss: "إخفاء",
```

The consent wording needs owner review before phase 4; flag it in the session report.

- [ ] **Step 4: Verify**

Run: `npx vitest run && npm run typecheck && npm run lint && npm run rtl:check`
Expected: all pass, including existing `ProfilePage` and `StatusPage` tests (add the new endpoint to their mocks if they fail on an unhandled request).

- [ ] **Step 5: Commit**: `feat: WhatsApp opt-in on the profile and a prompt on the status page`

---

### Task 17: Infrastructure

**Files:**
- Create: `infrastructure/modules/notification-alerts.bicep`
- Modify: `infrastructure/modules/container-app.bicep`, `infrastructure/main.bicep`, `.github/workflows/reusable-deploy-backend.yml`, `docs/github-setup.md`

**Interfaces:**
- Produces: `enableNotifications` (bool, default `false`), `notifyCron` (default `'*/5 * * * *'`), `alertEmail` (string, default `''`, given at deploy, never committed); job `caj-${prefix}-notify`.

- [ ] **Step 1: Add the job and secrets to `container-app.bicep`**

Add `param enableNotifications bool = false`, `param notifyJobName string = ''`, `param notifyCron string = '*/5 * * * *'`. Add `notificationSecrets` (Key Vault references `whatsapp-access-token`, `whatsapp-app-secret`, `whatsapp-verify-token`, `notifications-allowlist`) and matching `notificationSecretEnv`, concatenated onto the app and the `notify` job only when enabled, so `migrate` and `cleanup` never receive them.

`resource notifyJob ... = if (enableNotifications)` copies `cleanupJob`, with `replicaTimeout: 280`, `replicaRetryLimit: 0`, `cronExpression: notifyCron`, `args: ['notify']`, `OTEL_SERVICE_NAME: 'medical-notify'`.

- [ ] **Step 2: Add the alert module**

`notification-alerts.bicep` has one action group emailing `alertEmail` and four `Microsoft.Insights/scheduledQueryRules` scoped to Application Insights:

| Rule | KQL | Fires when |
|---|---|---|
| Failed or expired | `traces \| where message in ("notification_failed", "notification_expired")` | count > 0 in 15 min |
| Oldest due too old | `traces \| where message == "notify_run" \| where toint(customDimensions.oldest_due_age_seconds) > 1800` | count > 0 in 15 min |
| Missed runs | `traces \| where message == "notify_run"` | count < 1 in 15 min |
| Job failed | `traces \| where message == "notify_run_failed"` | count > 0 in 15 min |

- [ ] **Step 3: Wire `main.bicep`**

Add the parameters and `notifyJob: 'caj-${prefix}-notify'` in `names`. Add `notificationSettings`, unioned into `settings` only when enabled, with the plain-env names from spec section 10 given as parameters. Deploy the alert module only when `enableNotifications && !empty(alertEmail)`.

- [ ] **Step 4: Update the deploy workflow**

Add a step before "Create the new revision", guarded with `if: ${{ vars.NOTIFY_JOB_NAME != '' }}`, that runs `az containerapp job update --name "$NOTIFY_JOB_NAME" ... --image "$IMAGE"`. Do not add `NOTIFY_JOB_NAME` to the required-variables check. Document the variable in `docs/github-setup.md`.

- [ ] **Step 5: Verify locally, without deploying**

Run: `az bicep build --file infrastructure/main.bicep --stdout > /dev/null`
Expected: no errors or new warnings. **Do not run any deployment.** Mark all of this `NOT VERIFIED — requires Azure credentials` in the progress notes.

- [ ] **Step 6: Commit**: `feat: notify job and alert rules behind enableNotifications`

---

### Task 18: Documentation and final verification

**Files:**
- Modify: `docs/api.md`, `docs/security.md`, `docs/azure-deployment.md`, `docs/local-development.md`, `docs/architecture.md`, `docs/database.md`, `docs/progress.md`

- [ ] **Step 1: Update the documents**

| Document | Content |
|---|---|
| `docs/api.md` | The three endpoints, the webhook and the two 409 codes |
| `docs/security.md` | Extend L3 and L4 with Meta and AWS as recipients, marked as needing owner and legal sign-off. Add the webhook and stop-word behaviour |
| `docs/azure-deployment.md` | `enableNotifications`, the four Key Vault secrets that must exist first, phases 0–4, how to stop sending (`NOTIFICATIONS_MODE=off` on the job and the web app) |
| `docs/local-development.md` | Fake providers, running `manage.py send_notifications` locally |
| `docs/architecture.md`, `docs/database.md` | The `notifications` app and `Notification` table |
| `docs/progress.md` | New decisions (next free D-numbers), Done, open questions: cleanup/migrate telemetry gap, off-WhatsApp stop requests, Cloudflare routing, consent wording. Rewrite "Next session starts with" |

- [ ] **Step 2: Run everything**

```bash
cd backend && ruff check . && ruff format --check . \
  && .venv/Scripts/python manage.py makemigrations --check \
  && .venv/Scripts/python manage.py spectacular --file openapi.yaml --validate --fail-on-warn \
  && .venv/Scripts/python -m pytest -q
cd ../frontend && npm run typecheck && npm run lint && npm run rtl:check && npx vitest run && npm run build
```

Expected: everything passes. Report actual counts. Run `superpowers:verification-before-completion` before claiming the work is done.

- [ ] **Step 3: Check the spec's success list by hand**

For each bullet in spec section 1, name the test that proves it. Any bullet without one is a gap: add the test.

- [ ] **Step 4: Commit**: `docs: notifications architecture, security and deployment`

- [ ] **Step 5: Stop for the owner**

Report what is done and what is `NOT VERIFIED`, and ask before pushing or opening a PR. Phase 3 and later need explicit confirmation.
