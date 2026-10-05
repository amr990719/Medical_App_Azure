# Progress

Running log across Claude Code sessions. Each session appends to **Done**, records **Decisions**
and **Deviations from PROMPT.md**, updates **Open questions**, and rewrites **Next session starts with**.

## Done

### Session 1 — 2026-10-05 — Phase 1 (Inspect) + Phase 2 (Architecture)
- Inspected the target folder: it contained only `PROMPT.md`, `.agents/skills/azure-*-py` (four Azure
  Python SDK skills symlinked into `.claude/skills/`), `skills-lock.json`, `.claude/settings.local.json`
  and a local virtualenv `.medical_venv/`. No git repository, no code.
- Initialized git (`main`), wrote `.gitignore` (venvs incl. `.medical_venv/`, `node_modules/`, `.env*`,
  `dist/`, `__pycache__/`, coverage, Azurite data, `.claude/settings.local.json`, `reference/`).
- Cloned the Firebase prototype read-only to `../reference/medical-form` (outside the repo) and read
  `CalculationService.js`, `validateForm.js`, `validateReceiptImage.js`, `OcrService.js`,
  `FormContext.jsx`, `functions/index.js`. Confirmed defects 2.3 #4, #5, #8, #9, #11, #12 in the code.
- Created the monorepo skeleton (PROMPT.md §5 + §6 frontend structure): `backend/` with nine apps,
  `frontend/src/*`, `infrastructure/`, `.github/workflows/`, `docs/`, placeholder README,
  docker-compose, `.env.example`.
- Wrote `CLAUDE.md`, `.claude/skills/syndicate-form-rules/SKILL.md`, `docs/business-rules.md`,
  `docs/architecture.md`, `docs/plan.md` (Sessions 2–10), this file.

### Session 2 — 2026-10-05 — Phase 3A (backend core: models and business rules)
Built test-first (red → green for every module); no HTTP API, auth or frontend yet.
- **Toolchain:** the machine only had Python 3.11.9, so a user-local CPython 3.12.15 was installed
  with `uv` (no admin rights) and the project venv lives at `backend/.venv` (gitignored).
  Docker Desktop 29.7.2 / Compose v5.3.1.
- **Task 2.1** — Django 5.2 LTS project, settings `base/development/test/production`
  (`production.py` refuses to import with DEBUG, DEV_AUTH_ENABLED, a missing/short SECRET_KEY,
  missing/wildcard ALLOWED_HOSTS or missing DATABASE_URL; HTTPS/HSTS/secure-cookie settings,
  `sslmode=require`). `docker-compose.yml` with `postgres:16-alpine` + `azurite:3.35.0`
  (blob only), both with healthchecks and named volumes. pytest runs on PostgreSQL only.
- **Task 2.2** — `apps/reference`: `digits.py` (Eastern Arabic + Persian digits), `constants.py`
  (all enums with exact Arabic labels, 27 governorates, birth-governorate codes, kinship → fee key),
  `national_id.py` (parse/validate/mask; unknown governorate = warning; check digit not validated).
- **Task 2.3** — `document_rules.py`: the single rules table (member + per-kinship, age-aware child
  rule, configurable threshold, unknown birth year → under-16) + `rules_as_reference_data()`.
- **Task 2.4** — `accounts.User` (UUID pk, case-insensitive unique email, role, Entra oid/tid,
  unusable passwords) and `doctors.Doctor` (§12; national ID unique + CHECK format, never a pk).
- **Task 2.5** — `FeeSchedule` (versioned, one active per year, lock on use), FY 2026 seed data
  migration (reversible), pure fee engine `calculate_fees` / `get_tier` / `quote_for_application`.
  All nine §17.4 worked examples are table-driven tests with exact breakdowns and totals
  (750, 3025, 2925, 3475, boundaries, cap at 70 not 69, invalid years, empty-name row, 1825).
- **Task 2.6** — `InsuranceApplication` (partial unique one-active-per-doctor-per-year,
  reference-number ⇔ status CHECK, admin filter indexes), `ReferenceCounter`, `AdminNote`,
  `Beneficiary`, `Document` (one active per slot via NULLS NOT DISTINCT partial unique, type ⇔ owner
  CHECK, soft delete + active manager), `AuditLog` (append-only in the ORM **and** via a PostgreSQL
  trigger).
- **Task 2.7** — `beneficiaries/services.py` (upsert/delete with ownership + editability checks,
  digit normalization, kinship change soft-deletes that row's documents with audit, configurable
  spouse-gender and SON_MINOR rules, cross-application duplicate warnings), `common/exceptions.py`
  (`DomainError` family with §46 codes and envelope), `audit/services.py` (`record`, scrubbed
  metadata, HMAC-hashed IP), `documents/services.py` (`soft_delete_documents`).
- **Task 2.8** — `applications/validation.py`: all 18 §22 rules + §13/§14 consistency rules, every
  error returned at once with step, field path, code and Arabic message; `stage="form"|"submit"`;
  `common/arabic.py` (name normalization, mobile normalization).
- **Task 2.9** — `applications/transitions.py` (explicit 8-pair table) and `services.py`:
  `transition()` is the single status writer (row lock, role/ownership, notes, payment-confirmed
  check, audit), `submit()` (validation → fee snapshot → schedule lock → reference number on first
  submission only → submitted snapshot → audit), `generate_reference_number()`, `create_draft()`,
  `mark_receipt_uploaded()`, `set_payment_status()`. Concurrency tests run two/four threads against
  PostgreSQL; a mutation check (row lock removed → the test fails with 2 submissions) proved the
  test catches the race.
- **Task 2.10 (partial)** — `config/logging.py` (filter masking every 14+ digit run incl. Arabic
  digits, JSON formatter that re-masks output/tracebacks), wired into `LOGGING`;
  `manage.py grant_admin <email-or-oid>` (audited, idempotent).
- **Migrations reviewed** (django-safe-migration): every migration creates new tables, so no
  CONCURRENTLY / NOT VALID / lock_timeout patterns were needed; `migrate` → `migrate accounts zero`
  → `migrate` round trip passes (seed and trigger reverse cleanly).
- **PostgreSQL review** (live catalog): every FK has a supporting index; redundant indexes removed
  (LIKE `varchar_pattern_ops` indexes on email, blob_name, doctor national ID; FK indexes covered by
  composite/unique indexes). The reference-number LIKE index is kept for admin prefix search.
- **Result:** 391 tests passing on PostgreSQL 16, `ruff check` and `ruff format --check` clean,
  `manage.py check` clean, `makemigrations --check` reports no changes.

## Decisions

- **D1 — Same-origin API:** Azure Static Web Apps Standard with Container App as linked backend
  (PROMPT.md §4.1 option 1). Vite proxy locally.
- **D2 — Repository root** stays `Medical_App_Azure/` (existing folder) instead of creating a nested
  `medical-insurance-platform/` directory; the internal layout follows §5 exactly.
- **D3 — Project skill name:** `.claude/skills/syndicate-form-rules/` (requested by the user) instead of
  `medical-form-rules` named in PROMPT.md §3/§5. CLAUDE.md points to the new name.
- **D4 — Fiscal year** is a setting (`CURRENT_FISCAL_YEAR`, default 2026), not derived from the clock,
  so a schedule can be opened/closed deliberately.
- **D5 — Fee schedule storage:** tier amounts stored as JSON (`tier_fees`) on `FeeSchedule`, plus
  explicit columns for admin fees, age cap and registration-year floor; versions are immutable once
  referenced by a submission.
- **D6 — Blob access locally** via Azurite connection string; in Azure via `DefaultAzureCredential`
  and user-delegation SAS (≤5 min). Both behind one `BlobStorage` interface.
- **D7 — User model:** custom `accounts.User` (UUID pk, email, role, `entra_oid`, `entra_tid`)
  created in the first migration, before any other app.
- **D8 — Plan location:** `docs/plan.md` (user request) rather than the superpowers default
  `docs/superpowers/plans/`.
- **D9 — Test database:** PostgreSQL only (docker compose service / CI service container). No SQLite.

- **D10 — Python 3.12 via uv:** `backend/.venv` is created from a uv-managed CPython 3.12
  (`uv venv backend/.venv --python 3.12`); the system Python 3.11 is not used.
- **D11 — Fee key `grad_son`** (snake_case, matching the API convention) instead of `gradSon`.
  SKILL.md and business-rules.md updated.
- **D12 — Age cap = min(tier fee, 500):** the cap never raises a fee; identical to "replace with 500"
  for every FY 2026 amount. The note is added only when the cap changes the amount.
- **D13 — Tier boundaries are schedule data** (`FeeSchedule.tier_boundaries = [5, 10, 15]`).
- **D14 — Schedule lock:** first submission sets `locked_at`; a locked version refuses changes to
  any amount/boundary and refuses delete, but `is_active` can still be toggled.
- **D15 — ReferenceCounter:** UUID pk + unique `fiscal_year` (CLAUDE.md: all PKs are UUIDs);
  `INSERT … ON CONFLICT DO NOTHING` then `SELECT … FOR UPDATE` inside the submit transaction.
- **D16 — Doctor fields are blank/nullable** (the profile is completed while drafting);
  completeness is enforced by `validation.py`. `national_id` is nullable + unique.
- **D17 — One document per slot** via a single partial `UNIQUE … NULLS NOT DISTINCT` index
  (PostgreSQL ≥ 15) instead of two constraints.
- **D18 — Database CHECKs** for every enum column, national-ID format, `reference_number` present
  ⇔ status ≠ DRAFT (and format), document type ⇔ owner (member vs beneficiary) for active rows.
- **D19 — AuditLog append-only at DB level** (trigger). Its user FK is PROTECT (SET_NULL would be an
  UPDATE the trigger refuses).
- **D20 — `create_draft` raises `ACTIVE_APPLICATION_EXISTS`** when an active application exists
  (PROMPT.md §16.1), instead of returning it (plan Task 2.9).
- **D21 — Beneficiary deletion:** its documents are soft-deleted and detached (beneficiary NULL),
  then the row is deleted; the audit log keeps the ids.
- **D22 — Services re-check ownership** (defence in depth); admins cannot edit a doctor's draft.
- **D23 — Payment status:** admin may set CONFIRMED/REJECTED only while SUBMITTED, UNDER_REVIEW or
  NEEDS_CORRECTION and only after a receipt exists; NOT_UPLOADED/PENDING_REVIEW are server-only.
- **D24 — `validate_for_submission(stage="form")`** omits rules 16–17 from `errors`; `steps`
  always reflects the full submit evaluation so the stepper shows steps 4–5 incomplete.
- **D25 — `submitted_at`** = latest submission; the first submission time is in the audit log.
  Resubmission recomputes `fee_snapshot` with the active schedule.
- **D26 — Labels not given by the spec:** PaymentStatus `لم يتم رفع الإيصال / بانتظار التأكيد /
  مؤكد / مرفوض`; ScanStatus `قيد الفحص / سليم / مصاب / لم يتم الفحص`; Role `طبيب / مسؤول`.
- **D27 — No Django admin site** (`django.contrib.admin` not installed; the admin UI is the SPA);
  `User` has no `PermissionsMixin`/`is_staff`.
- **D28 — Azurite host port is configurable** (`AZURITE_BLOB_PORT`, default 10000). On this machine
  `127.0.0.1:10000` is held by another process (`kpm`), so a gitignored root `.env` sets 10100.

## Deviations from PROMPT.md

| # | PROMPT.md says | What we did | Why |
|---|---|---|---|
| 1 | §3/§5: `.claude/skills/medical-form-rules/SKILL.md` | `.claude/skills/syndicate-form-rules/SKILL.md` | explicit user instruction in Session 1 |
| 2 | §54 Phase 2: write plan with `writing-plans` (default path `docs/superpowers/plans/`) | `docs/plan.md` | explicit user instruction |
| 3 | §5 root folder `medical-insurance-platform/` | existing folder `Medical_App_Azure/` is the root | avoid a nested root; layout inside is identical |
| 4 | §54 phases 3–10 | re-cut into Sessions 2–10 (backend split in two, Azure integration + Docker image together, Bicep + CI together, docs last) | user-defined session boundaries; all phase content is covered |
| 5 | plan Task 2.1 pins DRF, django-filter, drf-spectacular, Pillow, python-magic and adds a Makefile | only Django, psycopg, django-environ (+ dev tools, gunicorn) | packages are added in Session 3 when first used; Makefile/scripts in Session 6 (§32) |
| 6 | plan Task 2.10 `seed_dev_data` and `config/checks.py` | seed deferred to Session 3; checks covered by the `production.py` import-time guard | seeded documents need the storage abstraction to create real blobs |
| 7 | plan: commit after every task | one commit for the session | explicit user instruction ("Phase 3A: backend core models and business rules") |
| 8 | plan 2.5 `calculate_fees(..., fiscal_year=...)`, `get_tier(reg, ws, *, fiscal_year)` | fiscal year taken from the schedule: `calculate_fees(schedule, …)`, `get_tier(schedule, reg, ws)` | a quote can never mix a schedule with another year |
| 9 | plan 2.9 `set_payment_status(..., note="")` | no `note` parameter | internal notes get their own audited service with the admin endpoints (Session 3) |
| 10 | §22 lists 18 messages | 6 extra Arabic messages (SKILL.md §6) for birth-year/ID mismatch, spouse gender, SON_MINOR age, beneficiary ID = member ID, missing review notes, approve without payment | §13/§14 rules needed user-facing messages |

## Open questions

Business questions 1–14 are tracked in `docs/business-rules.md` §10 (defaults implemented, to be
confirmed by the organization). Technical/environment questions for the user:

- **Q-T1** Azure subscription, region and Entra External ID tenant are not available in this session;
  Sessions 7–8 will generate everything and mark Azure-dependent checks `NOT VERIFIED — requires Azure credentials`.
- **Q-T2** Resolved: Docker Desktop 29.7.2 runs PostgreSQL 16 + Azurite.
- **Q-T3** Python resolved (uv-managed 3.12.15, D10). Node 22 LTS still to be checked in Session 4.
- **Q-T5** CI and Azure must use PostgreSQL ≥ 15 (`NULLS NOT DISTINCT`, D17); Bicep should pin 16.
- **Q-B15** (business) Confirm the Arabic payment-status labels (D26) and whether an admin may change
  a payment decision after APPROVED (currently refused).
- **Q-T4** The `rtl` plugin's `rtl_check.py` path must be located via the `rtl-ui` skill in Session 4.

## Next session starts with

**Session 3 — Backend API, auth, documents, OCR, audit** (`docs/plan.md` → Session 3, Tasks 3.1–3.10).
1. Environment: `docker compose up -d` from the repo root (both services must report `healthy`),
   then `cd backend`. On a fresh clone create the venv first:
   `<any python> -m pip install uv && uv python install 3.12 && uv venv .venv --python 3.12 &&
   uv pip install --python .venv/Scripts/python.exe -r requirements/dev.txt`.
   Run `.venv/Scripts/pytest -q` → expect **391 passed** before changing anything.
2. Add DRF, django-filter, drf-spectacular, Pillow, python-magic(-bin) to `requirements/base.txt`
   as Task 3.1 needs them; wire `DomainError.as_envelope()` into the DRF exception handler.
3. Views only call the existing services: `applications.services` (`create_draft`, `submit`,
   `transition`, `set_payment_status`, `mark_receipt_uploaded`), `beneficiaries.services`,
   `fees.services.quote_for_application`, `applications.validation.validate_for_submission`,
   `reference.document_rules.rules_as_reference_data`. Doctor serializers keep every protected
   field read-only (§16.2).
4. Task 3.7 must call `mark_receipt_uploaded` on receipt upload and `soft_delete_documents` for
   replacements; then implement the deferred `seed_dev_data` (deviation 6).
5. Load `syndicate-form-rules`, `django-expert` and `test-driven-development` first.
