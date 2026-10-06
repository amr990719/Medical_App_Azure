# Verification record (PROMPT.md §55)

Session 9, 2026-10-06, on Windows 10 + Docker Desktop 29.7.2, against the compose stack
(PostgreSQL 16 with TLS, Azurite 3.35, Django with development settings) and the production image.
Every command below was run in this session after the last code change; outputs are summarized
here (counts, exit codes). Anything that needs a real Azure subscription or Entra tenant is
marked **NOT VERIFIED — requires Azure credentials**.

## 1. §55 checklist

| # | Item | Result | Command (summary of output) |
|---|---|---|---|
| 1 | Frontend builds | ✓ | `cd frontend && npm run ci` → `vite build` OK, 0 `.map` files in `dist/` (exit 0) |
| 2 | TypeScript passes | ✓ | same run: `tsc --noEmit` (app) + `tsc --noEmit -p tsconfig.node.json` (Vite/Playwright) |
| 3 | Frontend unit tests pass | ✓ | same run: Vitest **281 passed in 41 files**; ESLint `--max-warnings 0` clean |
| 4 | RTL checker passes | ✓ | same run: `python scripts/rtl_check.py src` → `0 error(s), 0 warning(s) in 126 file(s)` |
| 5 | Backend starts | ✓ | production image on the compose network (`config.settings.production`, `DB_SSLMODE=require`): container `healthy`, uid 10001; `GET /api/health/` 200, `GET /api/ready/` 200 `{"database": "ok"}` |
| 6 | Django system checks (incl. `--deploy`, production settings) | ✓ | `python manage.py check` → no issues; in the image with **exactly the environment `main.bicep` sets** (`DB_AUTH_MODE=entra`, `KEY_VAULT_URL`, `CACHE_URL=dbcache://…`, `TRUSTED_PROXY_COUNT=2`, …; Azure values replaced by placeholders): `python manage.py check --deploy` → `System check identified no issues (0 silenced)`, with and without OCR (`azure_openai`); with `DEV_AUTH_ENABLED=true` → `ImproperlyConfigured` (exit 1) |
| 7 | Migrations exist and apply on a clean PostgreSQL | ✓ | `makemigrations --check --dry-run` → `No changes detected`; new empty database `verify_clean`: `migrate` applied **26** migrations, 0 unapplied, second `migrate` → `No migrations to apply`, FY 2026 fee schedule present (1 row); database dropped |
| 8 | Backend tests pass | ✓ | `docker compose exec backend pytest -q --ds=config.settings.test` → **960 passed** (pytest 9.1.1, Azurite tests included); `ruff check` + `ruff format --check` clean (233 files) |
| 9 | Docker image builds | ✓ | `docker build --no-cache --target runtime backend/` exit 0 (432 MB); rebuilt after every backend change |
| 10 | PostgreSQL configuration works | ✓ local / NOT VERIFIED on Azure | TLS connection from the production image (`DB_AUTH_MODE=password`, `sslmode=require`); Entra token auth is unit-tested with mocked credentials — **NOT VERIFIED — requires Azure credentials** |
| 11 | Document upload flow end to end (Azurite) | ✓ | Playwright `doctor-submit`, `mobile-form`, `print-a4` upload through the Vite proxy → Django → Azurite; pytest `-m azurite` round trips |
| 12 | OCR flow with the mock provider | ✓ | Playwright `doctor-submit`: "مسح تلقائي" on ID front/back, syndicate card and a birth certificate fills only empty fields; pytest `apps/ocr` (incl. new `test_extract_only_suggests_and_saves_nothing`) |
| 13 | Authorization tests exist and pass | ✓ | IDOR → 404 on applications, beneficiaries, documents (metadata + content), OCR, fees, validation, submit; protected-field writes ignored/refused; every allowed and forbidden transition; admin-only endpoints refuse doctors; role change now ends sessions (§3 below) |
| 14 | Blob integration exists | ✓ / NOT VERIFIED on Azure | `apps/documents/storage.py` (Azurite connection string locally, managed identity + user-delegation SAS ≤ 300 s in Azure) — **NOT VERIFIED — requires Azure credentials** |
| 15 | Entra OIDC BFF implemented | ✓ implemented, NOT VERIFIED | code flow + PKCE + state + nonce (MSAL), independent RS256/iss/aud/exp/nonce/tid validation, (oid, tid) mapping, admin MFA (`amr`) — unit-tested with a local JWKS; **NOT VERIFIED — requires Azure credentials** (no tenant, Q-T1/Q-T7) |
| 16 | Playwright e2e (doctor submit, admin approve, correction loop) | ✓ | `npx playwright test` twice in a row: **11 passed, 5 skipped** each run (each spec runs only in its own desktop/mobile project), no retries |
| 17 | Print view fits A4 | ✓ | `print-a4.spec.ts`: 10 beneficiaries with long names → `print-a4-doctor.pdf: 2 page(s)`, `print-a4-admin.pdf: 2 page(s)`; nothing wider than the page, no clipped field, no validation marks; `doctor-submit.spec.ts` → 2 pages |
| 18 | Bicep validates | ✓ build / NOT VERIFIED what-if | `az bicep build` main + 14 modules: exit 0, 0 warnings (Bicep 0.48.1, strict `bicepconfig.json`); `az bicep build-params` dev/staging/prod OK; `check-template-security.py` → 0 problems, `--self-test` 20/20; `what-if` — **NOT VERIFIED — requires Azure credentials** (subscription read-only, Q-T15) |
| 19 | CI/CD files exist | ✓ | 7 workflows; `rhysd/actionlint` 1.7.12 (with shellcheck) → exit 0, no findings; shellcheck `entrypoint.sh` clean |
| 20 | No secrets committed | ✓ | `gitleaks git` (13 commits) → `no leaks found`; `gitleaks dir` on the working tree: every hit is in gitignored virtualenvs (third-party code) plus one false positive in `.env.example` (two empty variable names); see §4 |
| 21 | README contains deployment commands | ✗ **not yet** | `README.md` is still the Session 1 placeholder; writing it is Session 10 (Task 10.1). Deployment commands exist in `docs/azure-deployment.md` |

Dependency audits: `pip-audit -r requirements/prod.txt` and the exact 77 packages frozen in the
production image → **No known vulnerabilities found**; `npm audit --omit=dev` and `npm audit` →
**0 vulnerabilities**. `requirements/dev.txt` had pytest 8.4.2 (PYSEC-2026-1845, dev only) →
raised to `pytest>=9.0.3,<10`.

## 2. PROMPT.md §2.3 — each prototype defect and the test that proves it stays fixed

| # | Defect not to reproduce | Proof |
|---|---|---|
| 1 | Owner-editable payment status | `apps/applications/tests/test_submit.py::test_doctor_cannot_set_payment_status`; `test_api.py::test_patch_protected_fields_ignored` (status, payment_status, reference_number, fee_snapshot, reviewer fields, …), `::test_patch_protected_payment_status_on_submitted_app_is_refused_and_unchanged` |
| 2 | Resubmit by client status write | `apps/applications/tests/test_api.py::test_resubmit_after_needs_correction_keeps_reference_number`; `test_transitions.py` (NEEDS_CORRECTION → SUBMITTED only through the transition service); e2e `correction-loop.spec.ts` |
| 3 | Public download URLs | `apps/documents/tests/test_api.py::test_content_requires_owner_or_admin` (anonymous 401, other doctor 404), `::test_upload_returns_summary_without_storage_details`, `::test_pdf_content_is_a_download_never_framed`; `test_storage.py::test_content_sas_ttl_at_most_300s_and_read_only`; Bicep guard `check-template-security.py` (`allowBlobPublicAccess=false`, container `publicAccess=None`, no shared keys) |
| 4 | Browser-side fee snapshot | `apps/fees/tests/test_engine.py::test_worked_examples` (§17.4 totals); `apps/applications/tests/test_submit.py::test_submit_writes_snapshot_and_audit`; `test_api.py::test_fees_of_a_submitted_application_are_the_frozen_snapshot`; `fee_snapshot` in the protected-field test |
| 5 | Browser-only validation | `apps/applications/tests/test_submit.py::test_submit_with_errors_raises_validation_failed_and_changes_nothing`; `test_api.py::test_submit_errors_return_every_message_grouped_by_step` |
| 6 | No national-ID uniqueness | `apps/doctors/tests/test_models.py` (IntegrityError), `apps/doctors/tests/test_api.py::test_concurrent_duplicate_national_id_one_wins`; `apps/beneficiaries/tests/test_constraints.py::test_beneficiary_duplicate_national_id_in_application_fails`; `apps/applications/tests/test_constraints.py::test_second_active_application_same_year_violates_constraint` |
| 7 | Upload-at-end, orphaned files | upload-on-select + autosave: `frontend/src/features/application-form/useApplicationDraft.test.tsx`, `SmartUpload` tests; orphans: `apps/documents/tests/test_cleanup.py::test_orphan_blob_without_metadata_removed_after_grace`, `::test_cleanup_removes_soft_deleted_after_grace` |
| 8 | Dropped Arabic digits | `frontend/src/components/form/NidInput.test.tsx` (typing/paste of ٠-٩); `apps/reference/tests/test_national_id.py::test_normalizes_arabic_digits_and_strips_separators`; `apps/doctors/tests/test_api.py::test_profile_accepts_arabic_digits`; e2e `mobile-form.spec.ts` types `٢٠١٥` |
| 9 | Browser-side OCR with exposed key | `apps/ocr/tests/test_api.py::test_anonymous_401`, `::test_rate_limit_31st_call_429`, `::test_rate_limit_is_per_user`, `::test_extract_only_suggests_and_saves_nothing` (new; mutation-checked red); SWA CSP `connect-src 'self'` (`staticWebAppConfig.test.ts`); production bundle grep for `openai|gemini|generativelanguage|api-key|AIza…` → no match |
| 10 | Committed Firebase config, EOL Node | gitleaks (history clean); `backend/Dockerfile` `python:3.12-slim`; workflows `node-version: "22"`, `python-version: "3.12"`; `package.json` `engines.node >=22` |
| 11 | Inconsistent child document rules | `apps/reference/tests/test_api.py::test_document_rules_come_from_the_single_rules_table`; frontend slots come from the server's `required_documents` (`BeneficiaryTable.test.tsx`, DocumentModal); e2e helper uploads exactly what the server asks for |
| 12 | Reference number on create | `apps/applications/tests/test_constraints.py::test_draft_cannot_carry_a_reference_number`; `test_reference_numbers.py::test_concurrent_submits_of_the_same_application_produce_one_number`; `test_api_concurrency.py::test_parallel_submissions_get_unique_sequential_reference_numbers` |

## 3. Defects found and fixed in this session

Each fix was test-first (red shown, then green). Details and rationale: `docs/security.md` §8.

| Id | Finding | Fix |
|---|---|---|
| V1 | Printed beneficiary names and the declared name were silently clipped by their inputs (found by the new 10-beneficiary print test) | print-only wrapping copy of the value, input hidden in print |
| V2 | The admin's masked national ID showed the red "14 digits" hint on the official printout | client ID hints only while the form is editable |
| V3 | `check --deploy` with the Bicep environment (`DB_AUTH_MODE=entra`) showed every process start still reading `database-password` from Key Vault; a Key Vault error stopped replicas from starting (= F7) | the password is read only in password mode |
| F1–F8 | Security review findings (throttle/audit client address, admin MFA on role change, upload body cap, expired sessions, PDF framing, source maps, Key Vault at startup, dev dependency) | see `docs/security.md` §8 |

## 4. Commands (reproducible)

```bash
# stack
npm run up
# backend
docker compose exec backend sh -c 'ruff check . && ruff format --check . && python manage.py check \
  && python manage.py makemigrations --check --dry-run && pytest -q --ds=config.settings.test'
# frontend (lint, tsc, vitest, rtl_check, build)
cd frontend && npm run ci && npx playwright test
# production image + deploy checks (bicep.env = the settings main.bicep sets, placeholders for Azure ids)
docker build --target runtime -t medical-backend:runtime backend/
docker run --rm --entrypoint python --env-file bicep.env -e DJANGO_SECRET_KEY=… -e ENTRA_CLIENT_SECRET=… \
  medical-backend:runtime manage.py check --deploy
# infrastructure
az bicep build --file infrastructure/main.bicep --outfile main.json   # + each module, build-params
python infrastructure/scripts/check-template-security.py main.json && \
  python infrastructure/scripts/check-template-security.py main.json --self-test
# workflows, secrets, dependencies
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest -no-color
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest git /repo
pip-audit -r backend/requirements/prod.txt && (cd frontend && npm audit --omit=dev)
```

Artefacts: `docs/screenshots/session-9/` (`print-a4-doctor.pdf`, `print-a4-admin.pdf`,
`mobile-{dashboard,form,payment,review,status}.png`); Session 5/6 screenshots refreshed by the
re-run specs.
