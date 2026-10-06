# Medical Syndicates Treatment Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. One session = one plan section below. Start every session by reading `docs/progress.md` → "Next session starts with", and end it by updating `docs/progress.md` and committing.

**Goal:** Build the production-ready Azure web application that digitizes the treatment-project subscription form (doctor wizard + admin review), as specified in `PROMPT.md`.

**Architecture:** React/TypeScript SPA on Azure Static Web Apps calling a same-origin `/api` proxied to Django + DRF on Azure Container Apps (BFF with Entra External ID session cookies). Django is the single authority for fees, validation, status transitions, document rules and reference data; data in Azure Database for PostgreSQL, files in a private Blob container, secrets in Key Vault, optional server-side OCR through Azure OpenAI. See `docs/architecture.md`.

**Tech Stack:** Python 3.12+, Django 5 LTS, DRF, psycopg 3, drf-spectacular, Pillow, python-magic, azure-storage-blob / azure-identity / azure-keyvault-secrets, openai (Azure), msal, azure-monitor-opentelemetry, pytest + factory_boy, ruff · Node 22, React 19, TypeScript strict, Vite, Tailwind CSS, React Router, TanStack Query, React Hook Form + Zod, Vitest + Testing Library, Playwright · Bicep, GitHub Actions (OIDC), Docker.

**Spec:** `PROMPT.md` (sections referenced as §N). Rules digest: `.claude/skills/syndicate-form-rules/SKILL.md`. Human rules: `docs/business-rules.md`.

## Global Constraints

- Python ≥ 3.12, Node 22 LTS; Django current LTS; PostgreSQL for dev, test and CI — never SQLite (§23, §53).
- Money is `int`/`Decimal`, never float (§17.1). All primary keys are UUIDs; national ID is never a PK (§12, §53).
- Fees, validation, transitions, document rules, reference data: server only; serializers mark `status`, `payment_status`, `reference_number`, `fee_snapshot`, `fee_schedule`, `review_notes`, `reviewed_by`, `reviewed_at`, `submitted_at` read-only for doctors (§16.2, §28).
- Never log full national IDs, tokens, cookies, document bytes, OCR payloads; mask `29•••••••••123` (§13, §38).
- Frontend: `<html lang="ar" dir="rtl">`, Cairo font, all strings in `frontend/src/i18n/ar.ts`, logical Tailwind utilities only (`ms- me- ps- pe- start- end- text-start`), `dir="ltr"` on numeric/ID/phone/email inputs, Eastern Arabic digits normalized both sides, `ar-EG` display formatting (§7).
- Theme tokens §7.2 and status colours §7.3 verbatim.
- API under `/api/v1/`, snake_case JSON, error envelope `{"error": {"code", "message", "fields"}}` with codes from §46.
- No secrets in Git; `.env.example` names only; never invent Azure IDs. Anything not verifiable without Azure is reported as `NOT VERIFIED — requires Azure credentials` (§53, §55).
- Documents only in private Blob; access through `/documents/{id}/content/` or ≤5-minute SAS (§19–20).
- `DEV_AUTH_ENABLED` only in development/test settings; production refuses to start with it (§27, §30).
- Commit at the end of every task; never push, create repos/PRs or Azure resources without the user's confirmation (§3, §54).

## Review Focus

Inputs the spec implies but no single rule names; each is pinned to a test in the owning task.

1. A national ID pasted with spaces, dashes or Eastern Arabic digits (`٢٩٥٠١٢٣-٠١٠١٢٣٤`) must normalize to 14 Western digits in both NidInput and the backend parser — Tasks 2.2 and 4.5.
2. Two concurrent `POST /submit/` requests for the same application must produce exactly one reference number and one `APPLICATION_SUBMITTED` audit entry — Task 2.9.
3. A beneficiary row with a kinship but no birth year must still get a deterministic document requirement (treated as age < 16) and a fee line (no cap) — Tasks 2.3 and 2.5.
4. A receipt that is a renamed PDF/EXE with `.jpg` extension or a 10×10 px image must be rejected by sniffing/decoding, not by extension — Task 3.7.
5. An admin `APPROVED` transition while `payment_status != CONFIRMED` and a doctor `PATCH` while status is `SUBMITTED` must both fail with the right code and leave no audit side effects — Tasks 2.9 and 3.5.

---

# Session 2 — Backend core

**Outcome:** Django project boots against PostgreSQL in docker compose; all domain models, constraints and migrations exist; FY 2026 fee seed applied; national ID, document rules, fee engine, validation, transitions and reference numbers are implemented as pure services with passing tests. No HTTP API yet (Session 3).

**Skills to load:** `syndicate-form-rules`, `django-expert`, `django-safe-migration`, `postgresql-best-practices`, `test-driven-development`.

### Task 2.1: Project scaffold, settings split, compose, pytest on PostgreSQL

**Files:**
- Create: `backend/manage.py`, `backend/config/__init__.py`, `backend/config/urls.py`, `backend/config/wsgi.py`, `backend/config/asgi.py`
- Create: `backend/config/settings/base.py`, `development.py`, `test.py`, `production.py`
- Create: `backend/requirements/base.txt`, `dev.txt`, `prod.txt`, `backend/pyproject.toml` (ruff + pytest config), `backend/pytest.ini` or `[tool.pytest.ini_options]`, `backend/conftest.py`
- Create: `docker-compose.yml` (services `postgres` 16-alpine with healthcheck, `azurite` `mcr.microsoft.com/azure-storage/azurite` blob only on 10000), `.env.example`, `Makefile`
- Test: `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: `DJANGO_SETTINGS_MODULE=config.settings.test` reads `DATABASE_URL` (default `postgres://medical:medical@localhost:5432/medical_test`); `base.py` exposes `CURRENT_FISCAL_YEAR: int = env.int("CURRENT_FISCAL_YEAR", 2026)`, `MAX_BENEFICIARIES = 10`, `REQUIRE_MEMBER_PHOTO = False`, `CHILD_NATIONAL_ID_AGE = 16`, `ENFORCE_SPOUSE_GENDER = True`, `ENFORCE_SON_MINOR_AGE = True`, `DEV_AUTH_ENABLED = False`, `OCR_ENABLED`, `OCR_PROVIDER = "mock"`; `INSTALLED_APPS` lists the nine `apps.*` packages with `AUTH_USER_MODEL = "accounts.User"`.
- `production.py` raises `ImproperlyConfigured` at import if `DEV_AUTH_ENABLED` is true or `SECRET_KEY`/`ALLOWED_HOSTS`/`DATABASE_URL` missing (§30).

- [ ] **Step 1: Write `backend/tests/test_smoke.py`** — `test_database_is_postgresql` asserts `connection.vendor == "postgresql"`; `test_fiscal_year_setting` asserts `settings.CURRENT_FISCAL_YEAR == 2026`.
- [ ] **Step 2: Run `cd backend && pytest -q`** → fails (no project).
- [ ] **Step 3: Create the project files above.** Use `django-environ` for env parsing; `DATABASES` via `env.db()` with `CONN_MAX_AGE=60`, `OPTIONS={"sslmode": env("DB_SSLMODE", default="prefer")}`. Pin: `Django>=5.2,<5.3`, `djangorestframework`, `psycopg[binary]>=3.2`, `django-environ`, `django-filter`, `drf-spectacular`, `Pillow`, `python-magic-bin` (Windows) / `python-magic`, `gunicorn` (prod), `pytest`, `pytest-django`, `factory-boy`, `ruff`. Write `docker-compose.yml` with named volumes `pgdata`, `azurite-data`, env `POSTGRES_USER/PASSWORD/DB=medical`, and a second database `medical_test` created by `docker/postgres-init.sql`.
- [ ] **Step 4: `docker compose up -d postgres azurite` then `pytest -q`** → 2 passed. Also `python manage.py check` → no issues.
- [ ] **Step 5: `ruff check . && ruff format --check .`** → clean. Commit `chore: django scaffold, settings split, compose, pytest on postgres`.

### Task 2.2: Reference constants and the national ID module

**Files:**
- Create: `backend/apps/reference/constants.py`, `backend/apps/reference/national_id.py`, `backend/apps/reference/digits.py`
- Test: `backend/apps/reference/tests/test_national_id.py`, `test_digits.py`

**Interfaces:**
- Produces (`constants.py`): `TextChoices` enums `SyndicateType(HUMAN_MEDICINE, PHARMACY, DENTISTRY, VETERINARY)`, `WorkStatus(WORKING, PENSIONER, DECEASED)`, `Gender(MALE, FEMALE)`, `Religion(MUSLIM, CHRISTIAN)`, `Kinship(MOTHER, FATHER, SON_MINOR, SON_UNIVERSITY, SON_GRADUATE, DAUGHTER, HUSBAND, WIFE)`, `DocumentType(...11 values §15)`, `ApplicationStatus(...6)`, `PaymentStatus(...4)`, `ApplicationType(FIRST_TIME, ADDITION)`, `ScanStatus(PENDING, CLEAN, INFECTED, SKIPPED)` — each with the exact Arabic labels from SKILL.md; `GOVERNORATES: list[str]` (27, order as §13); `BIRTH_GOVERNORATE_CODES: dict[str, str]`; `KINSHIP_FEE_KEY: dict[Kinship, Literal["spouse","child","gradSon","parent"]]`.
- Produces (`digits.py`): `normalize_digits(text: str) -> str` (٠-٩ and also Persian ۰-۹ → 0-9).
- Produces (`national_id.py`): `@dataclass(frozen=True) NationalIdInfo(value: str, date_of_birth: date, birth_year: int, gender: Gender, governorate_code: str, governorate_name: str | None, warnings: tuple[str, ...])`; `class InvalidNationalId(ValueError)` with `.message = "الرقم القومي يجب أن يكون 14 رقماً صحيحاً"`; `parse_national_id(raw: str, *, today: date | None = None) -> NationalIdInfo`; `is_valid_national_id(raw: str) -> bool`; `mask_national_id(value: str) -> str` → `29•••••••••123`.

- [ ] **Step 1: Write tests.** `test_normalizes_arabic_digits_and_strips_separators` (`"٢٩٥٠١٢٣ ٠١٠١٢٣٤"` with space and `"295-01-23-0101234"` → value `"29501230101234"`); `test_century_2_and_3`; `test_gender_from_digit_13` (odd→MALE, even→FEMALE); `test_invalid_date_rejected` (`29502300101234` Feb 30); `test_future_date_rejected` (century 3 with a date after `today`); `test_unknown_governorate_is_warning_not_error` (code `99`); `test_known_governorate_name` (`01` → القاهرة); `test_wrong_length_and_century_raise`; `test_mask`.
- [ ] **Step 2: Run** `pytest apps/reference -q` → ImportError.
- [ ] **Step 3: Implement** the three modules. Date parsing via `datetime.date(year, month, day)` in try/except → `InvalidNationalId`.
- [ ] **Step 4: Run** → all pass. **Step 5: Commit** `feat(reference): enums, governorates, national ID parser`.

### Task 2.3: Document rules table

**Files:**
- Create: `backend/apps/reference/document_rules.py`
- Test: `backend/apps/reference/tests/test_document_rules.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) DocumentRequirement(document_type: DocumentType, required: bool, label: str, ocr_capable: bool)`; `DOCUMENT_LABELS: dict[DocumentType, str]`; `OCR_CAPABLE_TYPES: frozenset[DocumentType]`; `member_document_requirements(*, require_photo: bool) -> list[DocumentRequirement]` (front, back, syndicate required; photo per flag; receipt required with a `stage="submit"` attribute); `beneficiary_document_requirements(kinship: Kinship, birth_year: int | None, *, fiscal_year: int, member_gender: Gender | None, child_id_age: int = 16) -> list[DocumentRequirement]`; `rules_as_reference_data(settings) -> dict` (serializable for `/reference-data/`).

- [ ] **Step 1: Tests** parametrized over every kinship: spouse → 3 required; parent → 1; child age 15 → birth cert required + national ID optional; age 16 → national ID required, birth cert not required (member male); age 20 + member FEMALE → birth cert required as well; `birth_year=None` → treated as <16 (Review Focus 3); SON_UNIVERSITY adds UNIVERSITY_ID; SON_GRADUATE adds INSURANCE_PRINT; `child_id_age=18` override shifts the boundary; photo flag toggles `PERSONAL_PHOTO.required`.
- [ ] **Step 2: Run → fail. Step 3: Implement. Step 4: Run → pass. Step 5: Commit** `feat(reference): single document rules table`.

### Task 2.4: Users and Doctor models

**Files:**
- Create: `backend/apps/accounts/models.py` (+ `managers.py`), `backend/apps/accounts/migrations/0001_initial.py`
- Create: `backend/apps/doctors/models.py`, `backend/apps/doctors/migrations/0001_initial.py`, `backend/apps/doctors/factories.py`, `backend/apps/accounts/factories.py`
- Test: `backend/apps/doctors/tests/test_models.py`, `backend/apps/accounts/tests/test_models.py`

**Interfaces:**
- Produces: `accounts.User(AbstractBaseUser, PermissionsMixin)`: `id UUID pk`, `email` unique (case-insensitive via `CIEmailField`-equivalent lower normalization), `role: Role(DOCTOR, ADMIN)` default DOCTOR, `entra_oid`, `entra_tid` (unique together, nullable for dev users), `is_active`, `is_staff`, `date_joined`; `USERNAME_FIELD = "email"`; `User.is_admin` property.
- Produces: `doctors.Doctor` exactly §12 with `national_id = CharField(14, unique=True)`, `date_of_birth`, `birth_year`, enum fields, `phone_number`, `treatment_card_number null=True`, index `(syndicate_type, syndicate_registration_number)`; `Doctor.masked_national_id` property; `on_delete=PROTECT` from User.
- Factories: `UserFactory`, `AdminUserFactory`, `DoctorFactory` (valid generated national IDs via a `fake_national_id(birth_year, gender)` helper in `backend/tests/helpers.py`).

- [ ] **Step 1: Tests:** `test_duplicate_national_id_raises_integrity_error`; `test_doctor_masked_national_id`; `test_user_email_is_case_insensitive_unique`; `test_create_admin_sets_role`.
- [ ] **Step 2: Run → fail. Step 3: Implement models + `makemigrations`.** Verify `0001_initial` of `accounts` has no dependency on other apps.
- [ ] **Step 4: Run → pass; `python manage.py migrate` on a fresh DB succeeds. Step 5: Commit** `feat(accounts,doctors): user and doctor models`.

### Task 2.5: Fee schedule model, FY 2026 seed, fee engine

**Files:**
- Create: `backend/apps/fees/models.py`, `migrations/0001_initial.py`, `migrations/0002_seed_fy2026.py` (data migration, reversible), `backend/apps/fees/services.py`, `backend/apps/fees/factories.py`
- Test: `backend/apps/fees/tests/test_engine.py`, `test_schedule.py`

**Interfaces:**
- Produces: `FeeSchedule(id UUID, fiscal_year int, version int, tier_fees JSON {"1": {"member":600,...}, ... "4"}, admin_fee_member_only int=150, admin_fee_with_beneficiaries int=175, age_cap_threshold int=70, age_cap_amount int=500, registration_year_min int=1950, is_active bool, created_by FK User null, created_at, locked_at null)`, unique `(fiscal_year, version)`, one active per fiscal year (partial unique). `FeeSchedule.is_locked` → True when any submitted application references it (Task 2.6 adds the FK).
- Produces (`services.py`): `@dataclass BeneficiaryInput(kinship: Kinship | None, name: str, birth_year: int | None)`; `@dataclass FeeLine(label: str, fee: int, note: str = "")`; `@dataclass FeeQuote(fiscal_year: int, tier: int, breakdown: list[FeeLine], admin_fee: int, total: int, is_valid: bool, error_message: str, schedule_id: str) -> .as_dict()`; `get_tier(registration_year: int, work_status: WorkStatus, *, fiscal_year: int) -> int`; `calculate_fees(schedule: FeeSchedule, *, fiscal_year: int, registration_year: int | None, work_status: WorkStatus | None, birth_year: int | None, beneficiaries: Iterable[BeneficiaryInput]) -> FeeQuote`; `active_schedule(fiscal_year: int) -> FeeSchedule` (raises `NoActiveFeeSchedule`); `quote_for_application(application) -> FeeQuote` (wires Doctor + Beneficiary rows; implemented after Task 2.6 models exist, tested in 2.9).

- [ ] **Step 1: Tests** — `test_fy2026_seed_exists` (schedule for 2026 v1 active with tier 3 spouse 1000); `test_worked_examples` parametrized with the nine rows of SKILL.md §4 (totals 750, 3025, 2925, 3475, tier boundaries, cap at 70 not 69, invalid years 1949/2027, empty-name row ignored with admin fee 150, FATHER 1950 → 1825); `test_spouse_note_text` equals `تم تطبيق سقف 500 ج (عمر 71 سنة)`; `test_beneficiary_without_birth_year_gets_tier_fee` (Review Focus 3); `test_addition_priced_like_first_time`; `test_locked_schedule_cannot_change` (`save()` raises `FeeScheduleLocked` when `locked_at` set).
- [ ] **Step 2: Run → fail. Step 3: Implement** model, seed migration (uses `apps.get_model`, reverse deletes the row), pure engine.
- [ ] **Step 4: Run → pass. Step 5: Commit** `feat(fees): schedule model, FY2026 seed, authoritative fee engine`.

### Task 2.6: Application, Beneficiary, Document, AdminNote, ReferenceCounter, AuditLog models

**Files:**
- Create: `backend/apps/applications/models.py` (`InsuranceApplication`, `ReferenceCounter`, `AdminNote`), `backend/apps/beneficiaries/models.py`, `backend/apps/documents/models.py`, `backend/apps/audit/models.py`, each `migrations/0001_initial.py`, factories per app
- Test: `backend/apps/applications/tests/test_constraints.py`, `backend/apps/beneficiaries/tests/test_constraints.py`, `backend/apps/documents/tests/test_constraints.py`

**Interfaces:**
- `InsuranceApplication` fields exactly §16.1 (`fee_schedule FK PROTECT null`, `reviewed_by FK User PROTECT null`), `EDITABLE_STATUSES = {DRAFT, NEEDS_CORRECTION}`, property `is_editable`; constraints: `UniqueConstraint(fields=["doctor","fiscal_year"], condition=~Q(status="REJECTED"), name="uniq_active_application_per_year")`, `reference_number` unique; indexes `(status, submitted_at)`, `(fiscal_year, status)`, `(payment_status)`.
- `ReferenceCounter(fiscal_year int pk, last_sequence int)`.
- `AdminNote(id, application FK, author FK, body, created_at)`.
- `Beneficiary` §14 + `UniqueConstraint(application,row_number)`, `UniqueConstraint(application,national_id, condition=Q(national_id__isnull=False))`, `CheckConstraint(row_number between 1 and 20)`; property `is_active` (kinship and name).
- `Document` §19 + `UniqueConstraint(application, beneficiary, document_type, condition=Q(deleted_at__isnull=True), name="uniq_active_document_per_slot")` (two constraints: one with `beneficiary__isnull=True`), `objects = ActiveDocumentManager` + `all_objects`.
- `AuditLog(id, user FK null SET_NULL, action CharField choices §39, object_type, object_id UUID, timestamp, ip_hash, metadata JSON)` with `save()` refusing updates (append-only) and no `delete()`.

- [ ] **Step 1: Tests:** `test_second_active_application_same_year_violates_constraint`; `test_rejected_application_allows_new_one`; `test_beneficiary_duplicate_national_id_in_application_fails`; `test_two_null_national_ids_allowed`; `test_row_number_unique`; `test_second_active_document_same_slot_fails_but_soft_deleted_allows`; `test_audit_log_is_append_only`.
- [ ] **Step 2: Run → fail. Step 3: Implement + `makemigrations`; add the `FeeSchedule.is_locked` query. Step 4: Run → pass; `migrate` from zero passes. Step 5: Commit** `feat: application, beneficiary, document, audit models with constraints`.

### Task 2.7: Beneficiary domain service

**Files:**
- Create: `backend/apps/beneficiaries/services.py`, `backend/apps/common/exceptions.py` (shared `DomainError(code: str, message: str, fields: dict[str, list[str]] | None = None, status_code: int = 400)` and subclasses `ValidationFailed`, `ApplicationNotEditable`, `InvalidStatusTransition`, `ActiveApplicationExists`, `DuplicateNationalId`, `PermissionDeniedError`, `RateLimited`)
- Test: `backend/apps/beneficiaries/tests/test_services.py`

**Interfaces:**
- Produces: `upsert_beneficiary(application, *, row_number: int, kinship: Kinship | None, full_name: str, birth_year: int | None, national_id: str | None, actor) -> Beneficiary` (normalizes digits; validates national ID format when present; rejects ID equal to member's; enforces `MAX_BENEFICIARIES`; raises `ApplicationNotEditable`; when kinship changes, soft-deletes the row's documents and records `DOCUMENT_DELETED`); `delete_beneficiary(beneficiary, actor)` (soft-deletes its documents); `beneficiary_warnings(beneficiary) -> list[str]` (cross-application duplicate national ID); `check_kinship_rules(beneficiary, member_gender, fiscal_year, settings) -> list[FieldError]` (spouse/gender, SON_MINOR ≤ 18).

- [ ] **Step 1: Tests:** `test_national_id_equal_to_member_rejected`; `test_eleventh_row_rejected`; `test_kinship_change_soft_deletes_documents`; `test_not_editable_raises`; `test_wife_requires_male_member_when_enforced`; `test_son_minor_over_18_flagged`; `test_cross_application_duplicate_is_warning`.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(beneficiaries): domain service and kinship rules`.

### Task 2.8: Submission validation module

**Files:**
- Create: `backend/apps/applications/validation.py`, `backend/apps/common/arabic.py` (`normalize_arabic_name(s) -> str`, `normalize_mobile(s) -> str`, `MOBILE_RE`)
- Test: `backend/apps/applications/tests/test_validation.py`, `backend/apps/common/tests/test_arabic.py`

**Interfaces:**
- Produces: `@dataclass FieldError(step: int, field: str, code: str, message: str)`; `@dataclass ValidationResult(errors: list[FieldError], steps: dict[int, bool], is_valid: bool, warnings: list[str]) -> .as_dict()` → `{"is_valid", "errors": [...], "by_step": {"1": [...], ...}, "steps_complete": {"1": true, ...}, "warnings"}`; `validate_for_submission(application, *, stage: Literal["form", "submit"] = "submit") -> ValidationResult` (stage `form` skips rules 16–17 and the receipt step; used by `/validation/` to compute stepper completion). Field paths: `member.national_id`, `beneficiaries[3].kinship`, `documents.NATIONAL_ID_FRONT`, `receipt`, `declaration.name`, `declaration.accepted`.

- [ ] **Step 1: Tests** — one test per rule 1–18 asserting the exact Arabic message and field path, using factories; `test_all_errors_returned_at_once` (empty application → ≥ 10 errors); `test_declaration_name_normalization` (`أحمد محمّد علي` vs `احمد محمد علي` → OK; the shadda is stripped too); `test_stage_form_ignores_receipt_and_acceptance`; `test_steps_complete_mapping`.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(applications): authoritative submission validation`.

### Task 2.9: Transition service, reference numbers, submit, payment status

**Files:**
- Create: `backend/apps/applications/services.py`, `backend/apps/applications/transitions.py` (the explicit table), `backend/apps/audit/services.py`
- Test: `backend/apps/applications/tests/test_transitions.py`, `test_reference_numbers.py`, `test_submit.py`

**Interfaces:**
- `audit.services.record(*, actor, action: str, obj, metadata: dict | None = None, request=None) -> AuditLog` (hashes IP with `SECRET_KEY` salt; strips keys in `SENSITIVE_KEYS = {"national_id", "review_notes_text"}`).
- `transitions.ALLOWED: dict[tuple[str, str], Transition(actor_role: Role, requires_notes: bool, requires_payment_confirmed: bool)]` with exactly the six rows of SKILL.md §5.
- `services.create_draft(doctor, *, fiscal_year: int, application_type=FIRST_TIME) -> InsuranceApplication` (returns the existing active one; `IntegrityError` → `ActiveApplicationExists`).
- `services.generate_reference_number(fiscal_year: int) -> str` — `ReferenceCounter.objects.select_for_update().get_or_create(...)`, must be called inside `transaction.atomic()`.
- `services.transition(application, *, to_status: ApplicationStatus, actor, review_notes: str = "") -> InsuranceApplication` — `select_for_update`, role check, table lookup, conditions, side effects (`reviewed_by/at`, `review_notes`), audit `APPLICATION_STATUS_CHANGED`.
- `services.submit(application, *, actor) -> InsuranceApplication` — lock, `validate_for_submission`, `quote_for_application` → `fee_snapshot`, first submission → reference number + `APPLICATION_SUBMITTED`, else `APPLICATION_RESUBMITTED`; `submitted_snapshot` = serialized member + beneficiaries + document ids; `FEE_SNAPSHOT_CREATED` audit.
- `services.set_payment_status(application, *, status: PaymentStatus, actor, note: str = "")` admin only, audit `PAYMENT_STATUS_CHANGED`.
- `services.mark_receipt_uploaded(application)` → `PENDING_REVIEW` (called by documents service in Session 3).

- [ ] **Step 1: Tests:** parametrized `test_every_allowed_transition_succeeds` and `test_every_other_pair_is_invalid` (all 36 pairs minus allowed); `test_needs_correction_requires_notes`; `test_approve_requires_confirmed_payment_and_writes_no_audit_on_failure` (Review Focus 5); `test_doctor_cannot_call_admin_transition`; `test_reference_number_format_and_sequence` (`MED-2026-000001`, `000002`); `test_concurrent_submits_produce_one_number` using two threads with `transaction.atomic` + `select_for_update` on a real PostgreSQL connection (Review Focus 2); `test_resubmit_keeps_reference_number`; `test_submit_stores_fee_snapshot_matching_example_2` (3025); `test_submit_with_errors_raises_validation_failed_and_changes_nothing`; `test_create_draft_returns_existing`.
- [ ] **Steps 2–5:** fail → implement → pass (`pytest -q` whole backend) → commit `feat(applications): transitions, atomic reference numbers, submit with fee snapshot`.

### Task 2.10: Logging filter, settings checks, seed command

**Files:**
- Create: `backend/config/logging.py` (`NationalIdMaskingFilter`, JSON formatter with `request_id`, `user_id`, `route`, `status`, `latency_ms`), `backend/config/checks.py` (Django system checks: production refuses `DEV_AUTH_ENABLED`, `ALLOWED_HOSTS=["*"]`, `DEBUG=True`), `backend/apps/reference/management/commands/seed_dev_data.py`, `backend/apps/accounts/management/commands/grant_admin.py`
- Test: `backend/config/tests/test_logging.py`, `backend/config/tests/test_checks.py`, `backend/apps/reference/tests/test_seed.py`

**Interfaces:**
- `seed_dev_data` is idempotent: FY2026 schedule (already seeded), admin `admin@example.test`, doctors `doctor1@example.test` (DRAFT application, example 2 data) and `doctor2@example.test` (SUBMITTED, reference number assigned), both with `entra_oid` null (dev auth).
- `grant_admin <email-or-oid>` sets role ADMIN and audits `ADMIN_ROLE_GRANTED`.

- [ ] **Step 1: Tests:** `test_filter_masks_14_digit_runs` (`"id 29501230101234 ok"` → `"id 29•••••••••234 ok"`); `test_production_settings_refuse_dev_auth` (import `config.settings.production` with env `DEV_AUTH_ENABLED=true` → `ImproperlyConfigured`); `test_seed_is_idempotent` (run twice → counts unchanged, doctor2 has `MED-2026-000001`).
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat: masked logging, production checks, dev seed and grant_admin`.

**Session 2 done when:** `docker compose up -d postgres azurite && cd backend && pytest -q` → all green on PostgreSQL; `python manage.py migrate` from an empty database applies every migration incl. the FY2026 seed; `python manage.py check` clean; `ruff check` clean; `docs/progress.md` updated; commit `Session 2: backend core`.

---

# Session 3 — Backend API, auth, documents, OCR, audit

**Outcome:** Every endpoint in §24 exists with object-level permissions, the §46 error envelope, OpenAPI schema, dev auth and Entra OIDC BFF, Blob-backed documents (Azurite locally), OCR with the mock provider, audit entries; all backend tests pass.

**Skills:** `syndicate-form-rules`, `django-expert`, `azure-storage-blob-py` (for the storage abstraction shape), `test-driven-development`.

### Task 3.1: Error envelope, exception handler, health endpoints, OpenAPI

**Files:** Create `backend/config/api/exceptions.py` (`api_exception_handler`), `backend/config/api/pagination.py` (`StandardPagination` page_size 25 max 100), `backend/config/api/renderers.py` if needed, `backend/config/health.py` (`/api/health/`, `/api/ready/` with `SELECT 1`), `backend/config/urls.py` (`/api/v1/` router, `/api/schema/`, `/api/docs/`); Test `backend/config/tests/test_errors.py`, `test_health.py`.

**Interfaces:** DRF `ValidationError` → 400 `VALIDATION_ERROR` with `fields`; `DomainError` → its `status_code` and `code`; `NotAuthenticated` → 401 `NOT_AUTHENTICATED`; `PermissionDenied` → 403 `PERMISSION_DENIED`; `Http404` → 404 `NOT_FOUND`; `Throttled` → 429 `RATE_LIMITED`; unhandled → 500 `SERVER_ERROR` with Arabic generic message, never a traceback.

- [ ] Tests: one per mapping asserting status and `error.code`; `test_ready_returns_503_when_db_down` (mock `connection.cursor` to raise); `test_schema_generates` (`SpectacularAPIView` returns 200 and contains `/api/v1/applications/`).
- [ ] fail → implement → pass → commit `feat(api): error envelope, health, openapi`.

### Task 3.2: Session auth, CSRF bootstrap, dev login, permissions

**Files:** Create `backend/apps/accounts/api/views.py` (`MeView`, `LogoutView`, `DevLoginView`, `DevUsersView`), `backend/apps/accounts/api/urls.py`, `backend/apps/accounts/permissions.py`, `backend/apps/accounts/api/serializers.py`; Test `backend/apps/accounts/tests/test_dev_auth.py`, `test_permissions.py`.

**Interfaces:** `GET /api/v1/auth/me/` → `{"user": {"id","email","role","display_name"}, "csrf_token": "..."}` (sets `csrftoken` cookie; 401 when anonymous). `POST /api/v1/auth/logout/`. Dev only (`DEV_AUTH_ENABLED`): `GET /api/v1/auth/dev/users/` lists seeded users, `POST /api/v1/auth/dev/login/ {"email"}` logs in. Permissions: `IsDoctor`, `IsAdmin`, `IsAuthenticatedActive`; mixin `DoctorScopedQuerySetMixin.get_queryset()` filters by `doctor__user=request.user`. Session settings: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_AGE=8h`, `SESSION_SAVE_EVERY_REQUEST=True` (idle timeout), `CSRF_COOKIE_HTTPONLY=False`, `CSRF_USE_SESSIONS=False`; production adds `Secure`.

- [ ] Tests: `test_dev_login_disabled_in_production_settings_returns_404`; `test_dev_login_sets_session_and_me_returns_role`; `test_unsafe_request_without_csrf_rejected`; `test_logout_clears_session`.
- [ ] fail → implement → pass → commit `feat(accounts): session auth, csrf bootstrap, dev login`.

### Task 3.3: Entra External ID OIDC BFF

**Files:** Create `backend/apps/accounts/oidc/client.py` (`OidcClient` built from settings `ENTRA_AUTHORITY`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` (from env/Key Vault), `ENTRA_REDIRECT_URI`, `ENTRA_SCOPES`, `ENTRA_ADMIN_REQUIRE_MFA=True`; uses `msal.ConfidentialClientApplication` with `initiate_auth_code_flow` / `acquire_token_by_auth_code_flow` which handle PKCE, state, nonce), `backend/apps/accounts/oidc/views.py` (`LoginView`, `CallbackView`), `backend/apps/accounts/oidc/claims.py` (`validate_claims(id_token_claims, *, expected_nonce) -> EntraIdentity(oid, tid, email, name, amr)`; `get_or_create_user(identity) -> User`), `backend/apps/accounts/oidc/urls.py`; Test `backend/apps/accounts/tests/test_oidc.py`.

**Interfaces:** `GET /api/v1/auth/login/?next=/dashboard` stores the MSAL flow dict in the session, 302 to Entra; `GET /api/v1/auth/callback/` exchanges the code, maps by `(oid, tid)` never by email alone, updates email/name, refuses `role=ADMIN` sessions when `"mfa" not in amr` and `ENTRA_ADMIN_REQUIRE_MFA`, logs in, redirects to a validated relative `next` (reject absolute URLs); `POST /auth/logout/` additionally returns `{"entra_logout_url"}`. Rate limit callback via DRF throttle `20/min` per IP.

- [ ] Tests (MSAL mocked with `unittest.mock.patch`): `test_login_redirects_to_authority_and_stores_flow`; `test_callback_creates_user_by_oid_tid`; `test_callback_existing_user_matched_by_oid_not_email` (same email, different oid → new user); `test_admin_without_mfa_refused`; `test_callback_rejects_open_redirect` (`next=https://evil`); `test_callback_error_from_entra_returns_envelope`.
- [ ] fail → implement → pass → commit `feat(accounts): Entra External ID OIDC BFF`. Note in progress.md: `NOT VERIFIED against a real tenant`.

### Task 3.4: Reference data and profile endpoints

**Files:** Create `backend/apps/reference/api/views.py` (`ReferenceDataView`, cache 1h, public to authenticated users), `backend/apps/doctors/api/{serializers,views,urls}.py`; Test `backend/apps/reference/tests/test_api.py`, `backend/apps/doctors/tests/test_api.py`.

**Interfaces:** `GET /api/v1/reference-data/` → `{"fiscal_year", "max_beneficiaries", "governorates": [...27], "syndicate_types": [{"value","label"}], "work_statuses", "religions", "genders", "kinships": [{"value","label","fee_key"}], "application_types", "statuses": [{"value","label"}], "payment_statuses", "document_types": [{"value","label","ocr_capable"}], "member_documents": [...], "beneficiary_document_rules": {"<KINSHIP>": {"always": [...], "under_age": [...], "from_age": [...], "if_member_female": [...], "age_threshold": 16}}, "ocr_enabled", "features": {"require_member_photo", "allow_pdf"}}`. `GET/PATCH /api/v1/profile/` → `DoctorProfileSerializer` (all §12 fields; `email` read-only from user; `national_id` write validates via `parse_national_id` and sets derived fields; `IntegrityError` → `DuplicateNationalId`; creates the Doctor row on first PATCH). PATCH is refused with `APPLICATION_NOT_EDITABLE` while the doctor's current-year application is not editable.

- [ ] Tests: `test_reference_data_shape_and_27_governorates`; `test_profile_patch_national_id_derives_birth_and_gender`; `test_profile_duplicate_national_id_returns_code`; `test_profile_accepts_arabic_digits`; `test_profile_locked_while_submitted`.
- [ ] fail → implement → pass → commit `feat(api): reference data and profile`.

### Task 3.5: Application endpoints

**Files:** Create `backend/apps/applications/api/{serializers,views,urls,filters}.py`; Test `backend/apps/applications/tests/test_api.py`, `test_api_security.py`.

**Interfaces:** `ApplicationViewSet` (doctor scoped): `list`, `create` (→ `services.create_draft`, 200 existing / 201 new), `retrieve`, `partial_update` (editable fields only: `application_type`, `work_status`, `declaration_name`, `declaration_accepted` bool → sets `declaration_accepted_at`; `APPLICATION_NOT_EDITABLE` otherwise), actions `fees` (GET → `quote_for_application().as_dict()`), `validation` (GET → `validate_for_submission(stage="form").as_dict()` plus `"submit_ready"` from stage submit), `submit` (POST → `services.submit`). `ApplicationSerializer` read-only: `status, payment_status, reference_number, fee_snapshot, fee_schedule, submitted_snapshot, review_notes, reviewed_by, reviewed_at, submitted_at, created_at, updated_at`; nested read-only `beneficiaries`, `documents` (summaries), `doctor` (profile).

- [ ] Tests: `test_doctor_sees_only_own_applications` (IDOR: other doctor's id → 404); `test_patch_protected_fields_ignored_or_rejected` for each of `status, payment_status, reference_number, fee_snapshot, review_notes` (assert unchanged in DB); `test_patch_when_submitted_returns_application_not_editable_and_no_audit` (Review Focus 5); `test_fees_endpoint_matches_example_2`; `test_validation_endpoint_groups_by_step`; `test_submit_happy_path_returns_reference`; `test_submit_errors_422_with_all_messages`; `test_create_twice_returns_same_draft`; `test_admin_cannot_use_doctor_endpoints_for_others`.
- [ ] fail → implement → pass → commit `feat(api): doctor application endpoints`.

### Task 3.6: Beneficiary endpoints

**Files:** Create `backend/apps/beneficiaries/api/{serializers,views,urls}.py`; Test `backend/apps/beneficiaries/tests/test_api.py`.

**Interfaces:** nested router `/applications/{id}/beneficiaries/` → `list`, `create`, `partial_update`, `destroy` calling Task 2.7 services; response includes `documents` map and `required_documents` (from Task 2.3) and `warnings`.

- [ ] Tests: `test_create_with_arabic_digits_normalized`; `test_row_limit_enforced`; `test_kinship_change_removes_documents`; `test_other_doctors_application_404`; `test_not_editable_409`.
- [ ] fail → implement → pass → commit `feat(api): beneficiaries`.

### Task 3.7: Documents — storage abstraction, upload validation, endpoints, cleanup

**Files:** Create `backend/apps/documents/storage.py` (`class BlobStorage(Protocol)`: `upload(blob_name, data: bytes, content_type) -> None`, `download(blob_name) -> bytes`, `delete(blob_name) -> None`, `exists(blob_name) -> bool`, `read_url(blob_name, *, ttl_seconds: int, content_type: str, filename: str) -> str | None`; `AzureBlobStorage` (connection string **or** account URL + `DefaultAzureCredential`, user-delegation SAS when credential-based; `read_url` returns None when SAS unavailable so the view streams instead); `InMemoryStorage` for tests; `get_storage()` from settings `BLOB_CONNECTION_STRING | BLOB_ACCOUNT_URL`, `BLOB_CONTAINER="medical-documents"`), `backend/apps/documents/validators.py` (`validate_upload(file, *, document_type) -> UploadInfo(content_type, size, sha256, width, height, extension)`: sniff with `magic`, allow `image/jpeg, image/png, image/webp` (+ `application/pdf` when `ALLOW_PDF_DOCUMENTS`, `image/heic` when `ALLOW_HEIC`), max `MAX_UPLOAD_BYTES=8*1024*1024`, Pillow `verify()` + reopen, receipt min 400×300, `PERSONAL_PHOTO` images only, filename sanitized to `[\w.-]{1,100}`; raises `DomainError` codes `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`, `IMAGE_TOO_SMALL`), `backend/apps/documents/naming.py` (`build_blob_name(application_id, beneficiary_id | None, document_type, extension) -> str` per §20), `backend/apps/documents/services.py` (`store_document(application, *, document_type, upload, uploaded_by, beneficiary=None) -> Document` replacing the active slot (soft-delete old + audit `DOCUMENT_REPLACED`), receipt → `mark_receipt_uploaded`; `delete_document`; `content_response(document, request)` → 302 SAS or `FileResponse`; audits `DOCUMENT_UPLOADED`, `DOCUMENT_DELETED`, `DOCUMENT_VIEWED`), `backend/apps/documents/api/{serializers,views,urls}.py`, `backend/apps/documents/management/commands/cleanup_blobs.py` (deletes blobs of documents soft-deleted > `BLOB_CLEANUP_GRACE_HOURS=24` and orphan blobs with no metadata); Test `backend/apps/documents/tests/test_validators.py`, `test_services.py`, `test_api.py`, `test_cleanup.py`, fixtures in `backend/tests/fixtures/` (tiny generated JPG/PNG/WEBP/PDF via Pillow/bytes at test time, no binaries committed).

**Interfaces:** `DocumentSummary` JSON: `{"id","document_type","beneficiary_id","original_filename","content_type","file_size","created_at","content_url": "/api/v1/documents/{id}/content/"}`. Endpoints per §24. Admin may read any document's content (audited `ADMIN_APPLICATION_VIEWED` on detail, `DOCUMENT_VIEWED` on content).

- [ ] Tests: `test_exe_renamed_jpg_rejected_by_sniffing` and `test_tiny_receipt_rejected` (Review Focus 4); `test_pdf_rejected_unless_flag`; `test_oversize_rejected`; `test_blob_name_pattern`; `test_upload_replaces_slot_and_soft_deletes_old`; `test_receipt_upload_sets_pending_review`; `test_content_requires_owner_or_admin` (IDOR 404); `test_content_sas_ttl_at_most_300s` (parse `se=` of the URL from a fake SAS generator); `test_delete_only_when_editable`; `test_cleanup_removes_soft_deleted_after_grace`.
- [ ] fail → implement → pass (Azurite running: run `test_api.py` once with `BLOB_CONNECTION_STRING=UseDevelopmentStorage=true` marked `@pytest.mark.azurite`) → commit `feat(documents): blob storage, upload validation, endpoints, cleanup job`.

### Task 3.8: OCR module with mock provider

**Files:** Create `backend/apps/ocr/normalizers.py` (`clean_national_id(raw) -> str`, `birth_year_from_id(id14) -> int | None`, `extract_year(raw) -> int | None`, `triple_name(full) -> str`, `map_governorate(text) -> str | None`, `map_enum(text, mapping) -> str | None`), `backend/apps/ocr/schemas.py` (JSON schemas + Arabic prompts per document type ported from the prototype, keys renamed to §21.3), `backend/apps/ocr/providers/base.py` (`class OcrProvider(Protocol): def extract(self, *, image: bytes, content_type: str, document_type: DocumentType) -> dict[str, Any]`), `providers/mock.py` (`MockOcrProvider` returns deterministic fixtures: ID front → example-2 member, back → ذكر/مسلم, syndicate → 2014/بشري, beneficiary → child), `providers/azure_openai.py` (stub class with constructor only; filled in Session 7), `backend/apps/ocr/services.py` (`extract_document(document, *, actor, request) -> OcrSuggestion(fields: dict, document_type)`: checks `OCR_ENABLED` → `OCR_UNAVAILABLE`, type in `OCR_CAPABLE_TYPES`, PDFs → `OCR_UNAVAILABLE` with message unless `pdf2image` available, throttle `OCR_RATE_LIMIT="30/hour"` per user → `RATE_LIMITED`, downloads bytes, calls provider, normalizes, audits `OCR_REQUESTED` with no values), `backend/apps/ocr/api/views.py` (`POST /documents/{id}/extract/`); Test `backend/apps/ocr/tests/test_normalizers.py`, `test_service.py`, `test_api.py`.

- [ ] Tests: normalizers per §21.4 (`٢٠٢١-٠٤-٢٨`→2021, `تاريخ القيد ٢٠٢١-٠٤-٢٨`→2021, `٢٨-٠٤-٢٠٢١`→2021, `عبد الرحمن محمد علي أحمد`→`عبد الرحمن محمد علي`, `أبو بكر ...`); `test_extract_returns_suggestions_and_saves_nothing`; `test_rate_limit_31st_call_429`; `test_disabled_returns_ocr_unavailable`; `test_non_ocr_type_400`; `test_other_users_document_404`; `test_audit_metadata_has_no_values`.
- [ ] fail → implement → pass → commit `feat(ocr): providers, normalizers, extract endpoint (mock)`.

### Task 3.9: Admin endpoints

**Files:** Create `backend/apps/applications/api/admin_views.py`, `admin_serializers.py`, `admin_filters.py` (django-filter: `status, payment_status, fiscal_year, governorate, syndicate_type, sub_syndicate, submitted_from, submitted_to`; search over `doctor__full_name, reference_number, doctor__phone_number, doctor__national_id` (exact 14 digits or masked suffix), ordering `submitted_at, reference_number, fee_snapshot__total, status`), `backend/apps/doctors/api/admin_views.py`, `backend/apps/fees/api/admin_views.py`, `backend/apps/audit/api/views.py`; Test `backend/apps/applications/tests/test_admin_api.py`, `backend/apps/fees/tests/test_admin_api.py`.

**Interfaces:** per §24 Admin block. `GET /admin/stats/` → counts per status + `receipts_pending`. Admin list rows show `masked_national_id`; `GET /admin/applications/{id}/?reveal_national_id=1` returns full ID and audits `NATIONAL_ID_REVEALED`. `POST .../transition/ {"to_status","review_notes"}`; `POST .../payment/ {"payment_status","note"}`; notes CRUD (create/list); `GET .../audit/`; `GET /admin/doctors/`, `/admin/doctors/{id}/`; fee schedules `GET list`, `POST` new version (`{"fiscal_year","tier_fees",...}` → version = max+1, deactivates the previous, audit `FEE_SCHEDULE_CHANGED`), `GET {id}`. Duplicate warnings (`beneficiary_warnings`) included in admin detail.

- [ ] Tests: `test_doctor_gets_403_on_admin_endpoints`; `test_filters_and_search_by_reference_and_masked_id`; `test_pagination_max_100`; `test_transition_endpoint_uses_table` (approve without payment → `INVALID_STATUS_TRANSITION`); `test_payment_confirm_then_approve`; `test_internal_note_not_visible_to_doctor`; `test_reveal_national_id_is_audited`; `test_new_fee_schedule_version_locks_previous`.
- [ ] fail → implement → pass → commit `feat(api): admin endpoints`.

### Task 3.10: Audit coverage and request logging middleware

**Files:** Create `backend/config/middleware.py` (`RequestIdMiddleware` sets `X-Request-ID`, structured access log with masked path), wire `ADMIN_APPLICATION_VIEWED`, `APPLICATION_CREATED`, `ADMIN_NOTE_ADDED` where missing; Test `backend/apps/audit/tests/test_coverage.py` parametrized over the §39 action list asserting each is produced by its endpoint/service.

- [ ] fail → implement → pass → commit `feat(audit): full action coverage, request id logging`.

**Session 3 done when:** `pytest -q` all green; `python manage.py spectacular --file schema.yml` succeeds and `frontend/src/api/schema.d.ts` can be generated from it with `openapi-typescript` (just verify the command, Session 4 commits the output); `curl` smoke through compose: dev login → create draft → upload a PNG to Azurite → extract (mock) → fees → submit returns `MED-2026-00000N`; `docs/api.md` drafted (endpoint list + link to `/api/docs/`); progress.md updated; commit `Session 3: backend API`.

---

# Session 4 — Frontend foundation and shared components

**Outcome:** Vite + React + TypeScript strict app with the theme, RTL, i18n, typed API client, session/guards, routing shell, layouts, UI kit and the paper-form shared components, all unit-tested; `rtl_check.py` passes.

**Skills:** `frontend-design`, `rtl-ui`, `test-driven-development`.

### Task 4.1: App scaffold, theme tokens, RTL, fonts, i18n skeleton

**Files:** Create `frontend/package.json` (scripts `dev`, `build`, `preview`, `lint`, `typecheck` (`tsc --noEmit`), `test` (vitest), `test:e2e` (playwright), `gen:api` (`openapi-typescript ../backend/schema.yml -o src/api/schema.d.ts`)), `tsconfig.json` (strict, `noUncheckedIndexedAccess`), `vite.config.ts` (proxy `/api` → `http://localhost:8000`, `@` alias), `index.html` (`<html lang="ar" dir="rtl">`, Cairo via Google Fonts `<link>`), `tailwind.config.ts` or `src/index.css` `@theme` with every §7.2 token + status colours + `fontFamily.sans = ["Cairo", "Segoe UI", "Tahoma", "sans-serif"]`, `src/main.tsx`, `src/App.tsx`, `src/i18n/ar.ts` (`export const ar = {...} as const` + `t(path)` helper), `src/utils/digits.ts` (`normalizeDigits`, `toArabicDigits`), `src/utils/format.ts` (`formatMoney(n) → "3٬025 ج.م"`, `formatDate(iso)`), `.eslintrc` with a rule forbidding `ml-|mr-|left-|right-` class literals (custom `no-restricted-syntax` regex); Test `src/utils/digits.test.ts`, `format.test.ts`.

- [ ] Tests: `normalizeDigits("٠١٢") === "012"`; `formatMoney(3025)` contains `3٬025` and `ج.م`; `formatDate("2026-10-03")` contains `أكتوبر`.
- [ ] `npm create vite@latest` (react-ts) → configure → `npm run typecheck && npm test` pass → commit `chore(frontend): scaffold, theme tokens, rtl, i18n`.

### Task 4.2: Typed API client and query layer

**Files:** Create `src/api/client.ts` (`apiFetch<T>(path, init?: {method, body, query}) : Promise<T>`: prefixes `/api/v1`, JSON by default, multipart when `body instanceof FormData`, sends `X-CSRFToken` from `csrftoken` cookie, `credentials: "same-origin"`, throws `ApiError(status, code, message, fields)` parsed from the §46 envelope, 401 → dispatches `session:expired` event), `src/api/schema.d.ts` (generated, committed), `src/api/types.ts` (hand-written aliases over schema + camelCase mappers `toCamel/toSnake`), `src/api/keys.ts` (`queryKeys.me, referenceData, applications.list, applications.detail(id), applications.fees(id), applications.validation(id), beneficiaries(id), admin.*`), `src/api/endpoints/*.ts` one module per resource; Test `src/api/client.test.ts` with `msw`.

- [ ] Tests: `sends csrf header on POST`; `parses error envelope into ApiError`; `multipart leaves content-type to browser`; `401 emits session:expired`.
- [ ] fail → implement → pass → commit `feat(frontend): typed api client`.

### Task 4.3: Session, guards, router shell, layouts

**Files:** Create `src/auth/useSession.ts` (TanStack query on `/auth/me/`), `src/auth/RequireAuth.tsx`, `src/auth/RequireRole.tsx`, `src/auth/signOut.ts` (POST logout, `queryClient.clear()`, redirect to Entra logout URL or `/signed-out`), `src/auth/DevLoginPanel.tsx` (shown only when `import.meta.env.DEV` and `/auth/dev/users/` responds), `src/router.tsx` with every §8 route (pages as lazy placeholders for Sessions 5–6), `src/layouts/{PublicLayout,DoctorLayout,AdminLayout}.tsx`, `src/pages/public/{LandingPage,SignedOutPage}.tsx`; Test `src/auth/RequireRole.test.tsx`, `src/pages/public/LandingPage.test.tsx`.

- [ ] Tests: unauthenticated → redirect to `/`; DOCTOR on `/admin/*` → redirect `/dashboard`; landing shows `تسجيل الدخول` and `إنشاء حساب` linking to `/api/v1/auth/login/?next=...`; sign-out clears query cache.
- [ ] fail → implement → pass → commit `feat(frontend): session, guards, routes, layouts, landing`.

### Task 4.4: UI kit

**Files:** Create `src/components/ui/{Button,Badge,StatusBadge,Card,Modal,Table,Skeleton,Toast,ConfirmDialog,Icon}.tsx` (+ `index.ts`), with `StatusBadge` mapping §7.3 colours and a pulsing dot for `UNDER_REVIEW`, check icon for `APPROVED`; `Modal` with focus trap + Escape + `aria-labelledby`; `Icon` with `mirror` prop applying `rtl:-scale-x-100` only to directional icons; Test `StatusBadge.test.tsx`, `Modal.test.tsx`, `ConfirmDialog.test.tsx`.

- [ ] fail → implement → pass → commit `feat(frontend): ui kit`.

### Task 4.5: Paper-form shared components

**Files:** Create `src/components/form/{NidInput,BoxStringInput,DashedField,RadioBoxGroup,ProgressStepper,ValidationErrorPanel,StickyActionBar,AutosaveIndicator}.tsx`; Test one `*.test.tsx` per component.

**Interfaces:** `NidInput({value, onChange(value: string), size?: "large"|"small", label, error?, readOnly?})` renders 14 boxes `dir="ltr"`, `role="group" aria-label`, hidden full-value input; `BoxStringInput({length: 26, ...})`; `RadioBoxGroup<T>({options: {value: T, label}[], value, onChange, label, name})` with real radios; `ProgressStepper({current: 1..5, completed: Set<number>})`; `ValidationErrorPanel({errors: {message: string, field?: string}[]})` with title `يرجى تصحيح الأخطاء التالية قبل المتابعة:` and `scrollIntoView` on mount; `StickyActionBar({start, end})`.

- [ ] Tests (NidInput): typing auto-advances; Backspace on empty moves back; paste `"٢٩٥٠١٢٣ ٠١٠١٢٣٤"` fills all 14 Western digits (Review Focus 1); non-digits ignored; `aria-label` present; `readOnly` disables edits. RadioBoxGroup: arrow keys move selection; selected box has inset style. ProgressStepper: labels hidden below 640px via class (`sm:inline`). ErrorPanel lists all messages.
- [ ] fail → implement → pass → commit `feat(frontend): paper-form shared components`.

### Task 4.6: RTL check and frontend CI script

- [ ] Locate `rtl_check.py` via the `rtl-ui` skill; add `npm run rtl:check` → `python <path>/rtl_check.py src`. Fix findings. Add `npm run ci` = `lint && typecheck && test -- --run && rtl:check && build`.
- [ ] `npm run ci` passes → commit `chore(frontend): rtl check and ci script`.

**Session 4 done when:** `npm run ci` green; `npm run dev` with compose backend shows the landing page in RTL with Cairo and dev login works to an empty dashboard placeholder; progress.md updated; commit `Session 4: frontend foundation`.

---

# Session 5 — Doctor flow

**Outcome:** The complete doctor journey works against the real API: dashboard, profile, paper-form replica with autosave, uploads + OCR merge, beneficiaries + DocumentModal, documents checklist, server fee quote, payment, review + submit, status, print.

**Skills:** `frontend-design`, `rtl-ui`, `syndicate-form-rules`.

### Task 5.1: Reference data + application draft state (port of FormContext)

**Files:** Create `src/features/reference/useReferenceData.ts` (`staleTime: Infinity`), `src/features/application-form/types.ts` (§10.1 `ApplicationFormState`, `BeneficiaryRow`, `DocumentSummary`), `src/features/application-form/mappers.ts` (API ⇄ form state), `src/features/application-form/useApplicationDraft.ts` (loads application + profile + beneficiaries, exposes `state`, `updateField`, `updateBeneficiary`, `updateBeneficiaryBatch`, `applyOcrSuggestions(fields)` (empty-fields-only merge), `saveStatus: "idle"|"saving"|"saved"|"error"`, debounced 800 ms PATCH per changed resource (profile vs application vs beneficiary row), retry with backoff 1s/2s/4s, `beforeunload` warning when dirty, invalidates `fees` + `validation` queries after a successful save), `src/features/application-form/ApplicationFormProvider.tsx`; Test `useApplicationDraft.test.tsx` (msw).

- [ ] Tests: `autosave PATCHes once after debounce`; `ocr merge fills only empty fields`; `kinship change clears row documents after confirm`; `save error sets status error and retries`; `read-only when status SUBMITTED`.
- [ ] fail → implement → pass → commit `feat(frontend): application draft state with autosave`.

### Task 5.2: Documents feature — SmartUpload, upload-on-select, OCR call

**Files:** Create `src/features/documents/{useUploadDocument.ts,useExtract.ts,SmartUpload.tsx,DocumentThumb.tsx,preCheck.ts}` (client pre-check: type, 8 MB, 400×300 for receipt, mirrors `validateReceiptImage.js`); Test `SmartUpload.test.tsx`.

- [ ] Tests: selecting a file uploads immediately with progress; `مسح تلقائي` shown only for OCR-capable types and when `ocr_enabled`; success/failure messages from `ar.ts` (`✓ تم الإرفاق: {name}`, `✓ تم استخراج البيانات — راجع الحقول أدناه وعدّل إن لزم`, `فشل المسح التلقائي. يمكنك إدخال البيانات يدوياً.`); pre-check rejects 5×5 px receipt before upload.
- [ ] fail → implement → pass → commit `feat(frontend): smart upload and ocr suggestions`.

### Task 5.3: MemberSection (header, photo, attachments panel, 12-col field grid)

**Files:** Create `src/features/application-form/{FormHeader,MemberSection,AttachmentsPanel,ApplicationTypeSelector}.tsx`; Test `MemberSection.test.tsx`.

- [ ] Tests: rows/fields in the §9.4 order and labels; national ID auto-fills birth year and gender when empty; mismatch shows inline error; governorate select has 27 options from reference data; email prefilled from session; below 768 px stacks (class assertions).
- [ ] fail → implement (follow §9.2–9.4 layout, paper styling: black 1.5 px borders, blue-700 ink, bold labels) → pass → commit `feat(frontend): member section`.

### Task 5.4: BeneficiaryTable, mobile cards, DocumentModal, documents checklist

**Files:** Create `src/features/beneficiaries/{BeneficiaryTable,BeneficiaryRow,BeneficiaryCard,DocumentModal,useRequiredDocuments.ts}.tsx`, `src/features/documents/DocumentsChecklist.tsx`; Test `BeneficiaryTable.test.tsx`, `DocumentModal.test.tsx`, `DocumentsChecklist.test.tsx`.

- [ ] Tests: exactly `max_beneficiaries` rows; paperclip appears once kinship set, grey → green when required docs attached; kinship change with docs asks confirmation then clears; clearing name+kinship deletes beneficiary after confirm; DocumentModal lists slots from `required_documents` with SmartUpload for OCR-capable types, title `مستندات المستفيد: {name}`, focus trap, Escape closes; checklist shows ✓/missing/optional for member + each active beneficiary.
- [ ] fail → implement → pass → commit `feat(frontend): beneficiaries table, document modal, checklist`.

### Task 5.5: FeeSummaryPanel, DeclarationSection, FormPage assembly

**Files:** Create `src/features/fees/{useFeeQuote.ts,FeeSummaryPanel.tsx}`, `src/features/application-form/DeclarationSection.tsx` (exact §9.7 text, red-underlined middle paragraph, inline dashed name input, signature block), `src/pages/application/FormPage.tsx` (sticky stepper, top bar with title `استمارة اشتراك — {fy}`, print and sign-out icons, autosave indicator, card max-w ~900 px, anchors `#member #beneficiaries #documents`, ValidationErrorPanel, FeeSummaryPanel, StickyActionBar with `تسجيل الخروج`, `طباعة`, `متابعة لرفع الإيصال` → GET validation → navigate or show panel), `src/pages/application/ApplicationRedirectPage.tsx` (`/application/:id` → right step by status/validation); Test `FeeSummaryPanel.test.tsx`, `FormPage.test.tsx`.

- [ ] Tests: panel renders server quote rows, `الدرجة {tier}`, total `الإجمالي`, skeleton while loading, error when `is_valid=false`; continue with errors shows panel with all messages and does not navigate; continue clean navigates to `/payment`; read-only mode disables inputs.
- [ ] fail → implement → pass → commit `feat(frontend): fee summary, declaration, form page`.

### Task 5.6: PaymentPage, ReviewPage, StatusPage, Dashboard, Profile, Print

**Files:** Create `src/pages/application/{PaymentPage,ReviewPage,StatusPage,PrintPage}.tsx`, `src/pages/doctor/{DashboardPage,ProfilePage}.tsx`, `src/features/applications/{useApplications.ts,useSubmissionStatus.ts (polling 30–60 s, stops when terminal),ApplicationCard.tsx,StatusTimeline.tsx}`, `src/features/application-form/PrintableForm.tsx` + `src/print.css` (`@page { size: A4; margin: 0 }`, `print-color-adjust: exact`, hides chrome/stepper/action bar/attachments/paperclips/modals); Test `PaymentPage.test.tsx`, `ReviewPage.test.tsx`, `DashboardPage.test.tsx`, `StatusTimeline.test.tsx`.

- [ ] Tests: payment page shows `ملخص الرسوم`, drop zone texts, uploaded bar with `إزالة`, continue → review; review page runs validation, requires acceptance checkbox, submit shows reference number; dashboard greeting `مرحباً د. {first}`, cards with StatusBadge, `+ تقديم طلب جديد` disabled when active app exists, NEEDS_CORRECTION card shows notes + `تصحيح وإعادة التقديم`; status timeline polls; print page includes reference number and submission date when present.
- [ ] fail → implement → pass → commit `feat(frontend): payment, review, status, dashboard, profile, print`.

**Session 5 done when:** `npm run ci` green; manual run through compose: dev login as doctor1 → form → mock OCR → beneficiaries (example 2) → fee 3٬025 → receipt → review → submit → reference shown → dashboard shows `مقدم`; progress.md updated; commit `Session 5: doctor flow`.

---

# Session 6 — Admin UI + local end-to-end environment

**Outcome:** Admin pages complete; the whole stack runs with `docker compose up` + `npm run dev`; seed, scripts and Playwright doctor flow work.

### Task 6.1: Admin dashboard, applications list, detail

**Files:** Create `src/pages/admin/{AdminDashboardPage,AdminApplicationsPage,AdminApplicationDetailPage,AdminPrintPage}.tsx`, `src/features/admin/{useAdminStats,useAdminApplications,useAdminApplication,FiltersBar,ApplicationsTable,DocumentViewer,TransitionButtons,PaymentPanel,NotesPanel,AuditList,RevealNationalId}.tsx`; Test `AdminApplicationsPage.test.tsx`, `AdminApplicationDetailPage.test.tsx`, `TransitionButtons.test.tsx`.

- [ ] Tests: tiles with §44 labels; table columns §44, server-side filters/search/sort/pagination reflected in query params; detail shows masked ID with audited reveal, documents in modal via `content_url`, fee snapshot, payment confirm/reject, only allowed transition buttons for the current status (from a `allowedTransitions(status, paymentStatus)` helper mirroring the table for UI only), notes (doctor-visible vs internal), audit list, print link.
- [ ] fail → implement → pass → commit `feat(frontend): admin dashboard, list, detail`.

### Task 6.2: Admin doctors and fee schedules pages

**Files:** Create `src/pages/admin/{AdminDoctorsPage,AdminDoctorDetailPage,AdminFeeSchedulesPage}.tsx`, `src/features/admin/{FeeScheduleTable,NewFeeScheduleForm}.tsx`; Test `AdminFeeSchedulesPage.test.tsx`.

- [ ] Tests: active schedule table matches FY2026 values; creating a new version asks confirmation and POSTs; locked versions are read-only.
- [ ] fail → implement → pass → commit `feat(frontend): admin doctors and fee schedules`.

### Task 6.3: Compose backend service, scripts, local-development doc

**Files:** Modify `docker-compose.yml` (add `backend` service: `build: ./backend`, dev settings, `DEV_AUTH_ENABLED=true`, `OCR_PROVIDER=mock`, `BLOB_CONNECTION_STRING=UseDevelopmentStorage=true` pointing at `azurite`, `depends_on` healthchecks, bind-mount source, command `python manage.py runserver 0.0.0.0:8000`), `backend/Dockerfile` (dev stage only for now; prod stage in Session 7), `backend/entrypoint.sh` (wait for DB, `migrate` only when `RUN_MIGRATIONS_ON_START=true` (dev default), `seed_dev_data` when `SEED_ON_START=true`), `Makefile` + root `package.json` scripts (`make up/down/migrate/seed/test-backend/test-frontend/lint/e2e`), `docs/local-development.md`.

- [ ] Verify: fresh clone → `docker compose up -d` → `curl localhost:8000/api/ready/` 200 → `cd frontend && npm ci && npm run dev` → dev login works. Commit `chore: compose backend service, scripts, local dev docs`.

### Task 6.4: Playwright setup and doctor happy path

**Files:** Create `frontend/playwright.config.ts` (baseURL `http://localhost:5173`, projects desktop + `Pixel 7` 390×844), `frontend/e2e/fixtures/` (generated images via script `e2e/make-fixtures.ts`), `frontend/e2e/helpers/devLogin.ts`, `frontend/e2e/doctor-submit.spec.ts`.

- [ ] Spec: sign in as doctor (fresh user via dev login with `?reset=1` support in `DevLoginView`), upload ID front → mock OCR fills fields → complete form with example 2 data → add WIFE + SON_MINOR with documents → fee panel shows `3٬025` → receipt → review → accept → submit → reference `MED-2026-` visible.
- [ ] `npm run test:e2e -- doctor-submit` passes → commit `test(e2e): doctor submit flow`.

**Session 6 done when:** `make up && make seed && npm run dev` gives a working doctor + admin app; `npm run ci` green; doctor e2e green; progress.md updated; commit `Session 6: admin ui and local e2e`.

---

# Session 7 — Azure integration + production Docker image

**Outcome:** Production code paths exist and are unit-tested with mocks: managed-identity Blob + user-delegation SAS, Key Vault settings loader, Entra-token PostgreSQL backend, Azure OpenAI OCR provider, Application Insights, production settings, multi-stage Docker image passing `check --deploy`. Everything Azure-facing is `NOT VERIFIED — requires Azure credentials`.

**Skills:** `azure-storage-blob-py`, `azure-identity-py`, `azure-keyvault-py`, `azure-monitor-opentelemetry-py`, `postgresql-best-practices`.

### Task 7.1: Blob storage via managed identity + user-delegation SAS
- Modify `backend/apps/documents/storage.py`: `AzureBlobStorage.from_settings()` picks connection string (dev) or `BlobServiceClient(account_url, credential=DefaultAzureCredential())`; `read_url` uses `get_user_delegation_key` cached for 1 h and `generate_blob_sas(..., permission=read, expiry=now+ttl≤300s, content_disposition, content_type)`; `credential` honours `AZURE_CLIENT_ID` for user-assigned identity.
- [ ] Tests (SDK mocked): `test_sas_expiry_le_300s`; `test_uses_connection_string_when_present`; `test_uses_default_credential_otherwise`. Commit `feat(documents): managed identity blob access and delegation sas`.

### Task 7.2: Key Vault settings loader
- Create `backend/config/secrets.py`: `load_secrets(names: list[str]) -> dict[str, str]` from `KEY_VAULT_URL` via `SecretClient(DefaultAzureCredential)`; env wins over Key Vault; used by `production.py` for `SECRET_KEY`, `ENTRA_CLIENT_SECRET`, `DATABASE_PASSWORD` (fallback). `.env.example` gains all names.
- [ ] Tests (mocked): `test_env_overrides_vault`; `test_missing_required_secret_raises_improperly_configured`. Commit `feat(config): key vault secrets loader`.

### Task 7.3: Entra-token PostgreSQL backend
- Create `backend/config/db/entra_postgres/base.py`: `DatabaseWrapper(psycopg DatabaseWrapper)` overriding `get_connection_params()` to set `password = credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token` when `DB_AUTH_MODE="entra"`, token cached until 5 min before expiry; `CONN_MAX_AGE` forced ≤ 1800 s; `sslmode=require`. `DB_AUTH_MODE="password"` keeps the standard backend.
- [ ] Tests (credential mocked): `test_token_used_as_password`; `test_token_refreshed_when_near_expiry`; `test_password_mode_unchanged`. Commit `feat(db): entra managed identity postgres backend`.

### Task 7.4: Azure OpenAI OCR provider
- Fill `backend/apps/ocr/providers/azure_openai.py`: `AzureOpenAIOcrProvider(endpoint, deployment, api_version, credential=DefaultAzureCredential via get_bearer_token_provider)` using `client.chat.completions.create(response_format={"type":"json_schema", ...schemas.py}, messages=[system Arabic prompt, user image data URL])`, timeout 30 s, maps SDK errors to `OCR_UNAVAILABLE`; `OCR_PROVIDER="azure_openai"` selects it; PDF first-page conversion via `pypdfium2` when installed.
- [ ] Tests (client mocked): `test_builds_json_schema_request`; `test_sdk_error_maps_to_ocr_unavailable`; `test_no_logging_of_payload` (caplog has no national ID). Write `docs/ocr.md`. Commit `feat(ocr): azure openai provider`.

### Task 7.5: Application Insights, production settings, startup checks
- Create `backend/config/telemetry.py` (`configure_azure_monitor()` when `APPLICATIONINSIGHTS_CONNECTION_STRING` set; Django/psycopg/requests instrumentation; log processor applying `NationalIdMaskingFilter`); finish `production.py`: `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER`, HSTS 1 year + preload, secure cookies, `SECURE_REFERRER_POLICY`, `X_CONTENT_TYPE_OPTIONS`, CSP header (`default-src 'none'; frame-ancestors 'none'`) for API responses, `DATA_UPLOAD_MAX_MEMORY_SIZE` 9 MB, CORS off, `ENTRA_*` required, `DEV_AUTH_ENABLED` refusal.
- [ ] Verify: `DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY=x ALLOWED_HOSTS=example.org DATABASE_URL=postgres://... ENTRA_...=x python manage.py check --deploy` → 0 warnings. Commit `feat(config): production settings, telemetry, deploy checks`.

### Task 7.6: Production Docker image
- Rewrite `backend/Dockerfile`: stage `builder` (python:3.12-slim, build wheels), stage `runtime` (slim, non-root `app` user, `libmagic1`, copy wheels, `collectstatic`, `HEALTHCHECK CMD curl -f http://localhost:8000/api/health/`, `CMD gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 60 --access-logfile -`), stage `dev` for compose. `entrypoint.sh`: production never migrates (`RUN_MIGRATIONS_ON_START` default false); a `migrate` command mode for the Container Apps job; `cleanup` mode for the cleanup job.
- [ ] Verify: `docker build -t medical-backend --target runtime backend/` succeeds; `docker run --rm medical-backend python manage.py check` passes with env; image runs as non-root (`whoami` → app). Commit `feat(docker): multi-stage production image`.

**Session 7 done when:** backend tests green incl. mocked Azure paths; `check --deploy` clean; prod image builds and starts; `docs/security.md` drafted (controls + legal/organizational decisions: religion field, OCR processing, retention, region, admin access, breach procedure); progress.md lists every `NOT VERIFIED` item; commit `Session 7: azure integration and production image`.

---

# Session 8 — Bicep, Entra scripts, GitHub Actions, GitHub setup docs

**Outcome:** Complete, validated infrastructure-as-code, Entra registration scripts, CI/CD workflows and the documentation to run them. Deployment itself is not executed.

**Skills:** `azure:azure-prepare` (for Bicep patterns; do NOT run `azure-deploy`), `azure:entra-app-registration`, `azure:azure-validate`.

### Task 8.1: Bicep modules
- Create `infrastructure/main.bicep` (resource-group scope; params `environmentName`, `location`, `baseName`, `enableOcr`, `enablePrivateNetworking=false`, sizes, `postgresBackupRetentionDays`, `minReplicas`, `maxReplicas`, `httpConcurrency`; `uniqueString(resourceGroup().id)` suffix; tags on all) and every module in §33: `identity`, `monitoring`, `key-vault` (RBAC mode, soft delete + purge protection), `storage` (private container `medical-documents`, soft delete 14 d, versioning, no public access, TLS 1.2), `postgres` (Flexible Server, Entra auth enabled + password optional, Burstable B1ms default, PITR retention param, geo-backup param, TLS), `container-registry`, `container-apps-env` (Log Analytics linked), `container-app` (Django app with min/max replicas, HTTP scaling, secrets as Key Vault references via identity, probes on `/api/health/` and `/api/ready/`; plus `migrate` job (manual trigger) and `cleanup` job (cron)), `static-web-app` (Standard, linked backend = container app), `openai` (conditional, vision deployment param), `role-assignments` (Storage Blob Data Contributor, Key Vault Secrets User, AcrPull, Cognitive Services OpenAI User). Parameters `parameters/{dev,staging,prod}.bicepparam`.
- [x] Verify: `az bicep build --file infrastructure/main.bicep` succeeds for every module (no Azure login needed); `az bicep lint` clean; `what-if` documented as `NOT VERIFIED — requires Azure credentials`. Commit `feat(infra): bicep modules and parameters`.

### Task 8.2: Entra and PostgreSQL identity scripts
- Create `infrastructure/scripts/create-entra-app.sh` (+ `.ps1`): creates the External ID app registration (web redirect URIs for each env, ID tokens off, client secret → Key Vault, optional Google IdP note), prints the values for `ENTRA_*`; `infrastructure/scripts/setup-postgres-entra.sh`: sets the Entra admin, creates the managed-identity role with `pgaadauth_create_principal`, grants privileges; `infrastructure/scripts/grant-github-oidc.sh`: federated credentials for the GitHub repo/environments. Each script is idempotent, uses `set -euo pipefail`, never embeds IDs. `docs/entra-setup.md` step by step (tenant creation, user flow with Arabic, MFA conditional access for admins, redirect URIs, scripts).
- [x] Verify: `bash -n` + `shellcheck` clean; PowerShell `-Syntax` parse. Commit `feat(infra): entra and identity scripts, entra docs`.

### Task 8.3: GitHub Actions workflows
- Create `.github/workflows/frontend.yml` (§36 chain, `Azure/static-web-apps-deploy` with deployment token from secrets or OIDC-managed), `backend.yml` (ruff → pytest with `postgres:16` service → `docker/build-push-action` → ACR login via `azure/login` OIDC → `az containerapp job start --name migrate` and wait → `az containerapp update --image`), `infrastructure.yml` (`bicep build` + `what-if` on PR, `az deployment group create` on main with environment protection), optional `e2e.yml` (compose + Vite + Playwright with dev auth and mock OCR). Secrets/vars referenced by name only: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `ACR_NAME`, `CONTAINER_APP_NAME`, `SWA_DEPLOYMENT_TOKEN`.
- [x] Verify: `actionlint` clean. Commit `ci: github actions for frontend, backend, infrastructure, e2e`.

### Task 8.4: Deployment and GitHub setup documentation
- Write `docs/azure-deployment.md` (exact `az` commands: login, resource group, `az deployment group create` per env, run scripts, set Key Vault secrets, build/push image, run migrate job, link SWA backend, enable OCR, cost section §52 with dev vs prod defaults and drivers, backups/restore §48, migration procedure §37 with rollback) and `docs/github-setup.md` (create repo, environments dev/staging/prod with reviewers, OIDC federated credentials, secrets/variables list, branch protection, first push). State clearly that no push/repo creation happens without confirmation.
- [x] Commit `docs: azure deployment and github setup`.

**Session 8 done when:** every Bicep file builds; scripts parse; workflows lint; docs contain copy-pasteable commands; progress.md updated; commit `Session 8: infrastructure and ci/cd`.

---

# Session 9 — Full testing + security review

**Outcome:** Every §55 verification item is executed and recorded; remaining Playwright specs exist and pass; a security review pass is done and findings fixed.

**Skills:** `verification-before-completion`, `security-review` / security-guidance, `systematic-debugging`, `playwright`.

### Task 9.1: Remaining end-to-end specs
- Create `frontend/e2e/admin-approve.spec.ts` (admin finds the seeded application → confirm payment → under review → approve; doctor sees `مقبول`), `frontend/e2e/correction-loop.spec.ts` (admin requests correction with note → doctor sees note, fixes, resubmits → same reference number), `frontend/e2e/print-a4.spec.ts` (`page.pdf({format:"A4"})` → page count ≤ 2 via `pdf-lib`), `frontend/e2e/mobile-form.spec.ts` (390×844: no horizontal scroll `document.documentElement.scrollWidth <= innerWidth`, form submittable).
- [x] All specs pass → commit `test(e2e): admin, correction loop, print, mobile`.

### Task 9.2: Full verification run
- [x] Run and record outputs in `docs/verification.md`: `npm run ci` (build, tsc, vitest, rtl_check), `pytest -q` (counts), `python manage.py check --deploy` with production settings, `migrate` on an empty database, `docker build`, compose doctor flow, OCR mock flow, authorization tests, Playwright suites, `az bicep build`, `actionlint`, secret scan (`gitleaks detect` or `trufflehog filesystem .`), `pip-audit`, `npm audit --omit=dev`. Mark Azure-dependent items `NOT VERIFIED — requires Azure credentials`.
- [x] Fix every failure found (systematic-debugging), re-run, commit `test: full verification pass`.

### Task 9.3: Security review
- [x] Run the `security-review` skill over auth (OIDC, session, CSRF, MFA refusal), uploads (sniffing, size, path, SAS TTL), permissions (IDOR on each resource, protected fields), logging (masking), rate limits (callback, OCR, uploads), headers/cookies in production settings, Bicep (public access, TLS, RBAC). Add tests for any gap; fix findings; finalize `docs/security.md` (controls table + items needing legal/organizational decisions). Commit `fix(security): review findings`.

**Session 9 done when:** `docs/verification.md` lists every §55 item with PASS or `NOT VERIFIED — requires Azure credentials` and the command used; no open high findings; progress.md updated; commit `Session 9: testing and security review`.

---

# Session 10 — Documentation + final report

### Task 10.1: README and docs set
- Write root `README.md` per §50 (ASCII architecture, exact local setup commands, every environment variable explained, migrations, seeding, tests backend/frontend/e2e, Docker, Azure prerequisites, Entra setup, infra deployment commands, app deployment, enabling OCR, granting admin, troubleshooting list from §50). Complete `docs/database.md` (Mermaid ER from the real models + constraints/indexes), `docs/api.md` (endpoint table + error codes + link to `/api/docs/`), refresh `docs/architecture.md`, `docs/business-rules.md`, `docs/ocr.md`, `docs/local-development.md`, `docs/security.md`.
- [ ] Verify every command in the README by running it (or marking `NOT VERIFIED`). Commit `docs: readme and documentation set`.

### Task 10.2: Final report
- Write `docs/final-report.md` with the 15 items of §56 (architecture, tree (`git ls-files` summary), schema, endpoints, Azure services, env vars, local instructions, Entra steps, deployment steps, cost drivers, security decisions, prototype features ported + §2.3 defects fixed checklist, limitations, open business questions (14), tests executed + results from `docs/verification.md`). Exact paths and commands only.
- [ ] Update `docs/progress.md` final state; commit `Session 10: documentation and final report`.

**Session 10 done when:** README commands verified; final report complete; repository clean (`git status`), all local commits present, nothing pushed without confirmation.

---

## Self-review notes (Session 1)

- Spec coverage: §1–§58 mapped — §9 (5.3–5.5), §10 (5.1), §11 (4.5, 5.2), §12–17 (2.2–2.9), §18–20 (3.7, 5.6, 7.1), §21 (3.8, 7.4), §22 (2.8), §23–25 (2.1, 2.6, 3.x), §26 (7.3), §27 (3.2–3.3, 8.2), §28 (3.2, 3.5–3.9), §29 (7.2), §30 (7.5), §31 (7.6), §32 (6.3), §33 (8.1), §34 (8.1, security.md), §35 (8.1), §36 (8.3), §37 (7.6, 8.3, 8.4), §38 (2.10, 7.5), §39 (2.9, 3.10), §40 (2.4, 2.6, 2.9), §41 (2.8 + Zod in 5.x), §42 (tests across tasks + 6.4, 9.1), §43 (5.6), §44 (6.1–6.2), §45 (3.1, 3.9), §46 (3.1), §47–49 (7.5, 8.1, 8.4, security.md), §50–51 (10.1), §52 (8.4), §55–56 (9.2, 10.2), §57 (business-rules.md).
- Type consistency: `FeeQuote`, `ValidationResult`, `DomainError`, `BlobStorage`, `OcrProvider`, `DocumentSummary`, `ApplicationFormState` names are used identically across sessions.
- Review Focus items 1–5 are pinned to tests in Tasks 2.2/4.5, 2.9, 2.3/2.5, 3.7, 2.9/3.5.
