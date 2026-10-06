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

### Session 3 — 2026-10-05 — Phase 3B (API, auth, documents, OCR, audit)
Built test-first on top of the Session 2 models and services (no rewrite; services were only
extended). Each module's tests were written and seen failing before the code; the one exception
is the N+1 query-count guard on the application detail, added afterwards as a regression guard.
- **Toolchain:** DRF 3.18, django-filter 26, drf-spectacular 0.30, Pillow 12, filetype 1.2,
  azure-storage-blob 12.31, azure-identity 1.26, msal 1.39, PyJWT 2.15 (`requirements/base.txt`).
  Node v22.11 / npm 11.7 are installed (Q-T3 resolved for the frontend).
- **Task 3.1** — `config/api/exceptions.py`: every error is the §46 envelope with Arabic messages
  (DRF/Django exceptions mapped, nested field errors flattened to dotted paths, submission errors
  carry `errors` with wizard steps, unhandled → generic 500 without traceback); JSON 404/403/400/500
  and CSRF-failure views; `StandardPagination` (25, max 100); `/api/health/` (no DB) and
  `/api/ready/` (`SELECT 1`, 503); OpenAPI at `/api/schema/` + `/api/docs/` behind `API_DOCS_ENABLED`.
- **Task 3.2** — Session auth with a 401 challenge, `IsAuthenticatedActive` / `IsDoctor` / `IsAdmin`,
  `SessionOnlyBackend` (no password authentication at all), HttpOnly SameSite=Lax cookie, idle
  (2 h) + absolute (12 h) timeouts, `/auth/me/` (CSRF bootstrap, also on 401), `/auth/logout/`
  (+ Entra logout URL), dev login (`/auth/dev/users/`, `/auth/dev/login/`, CSRF enforced, 404 unless
  `DEV_AUTH_ENABLED`), `User.display_name` (additive migration), `seed_dev_data` command
  (deviation 6 closed).
- **Task 3.3** — Entra External ID OIDC BFF: MSAL authorization code flow with PKCE/state/nonce,
  independent ID-token validation (RS256 against the tenant JWKS, issuer, audience, expiry, nonce,
  tenant), user mapped by `(oid, tid)` only, email/name refreshed, admin sessions refused without
  `mfa` in `amr` (configurable), safe relative `next`, callback throttled 20/min.
  **NOT VERIFIED — requires Azure credentials** (tested with a faked MSAL client and locally signed
  RS256 tokens only).
- **Task 3.4** — `/reference-data/` (all enums, 27 governorates, kinships with fee keys, THE
  document-rules table, flags, upload limits) and `/profile/` (`doctors/services.py`: national ID
  derives DOB/birth year/gender, conflicts rejected, the DB constraint decides duplicates incl. a
  two-thread race, locked while submitted). Arabic digits normalized by shared serializer fields
  (`apps/common/fields.py`).
- **Task 3.5** — Doctor application endpoints (list, create-or-return, retrieve with nested
  beneficiaries/documents, PATCH of the four editable fields only, `fees`, `validation`, `submit`);
  services `get_or_create_draft`, `update_draft`. IDOR tests on every route; every protected-field
  write attempt asserted unchanged in the database; a refused PATCH leaves no audit entry.
- **Task 3.6** — Beneficiary endpoints (nested; `add_beneficiary`, `update_beneficiary`), lowest
  free row, row limit, kinship change removes documents, IDOR through both ids.
- **Task 3.7** — Documents: `storage.py` (`BlobStorage` protocol; `AzureBlobStorage` for
  Azurite/Azure with ≤300 s read-only single-blob SAS — account key locally, user-delegation key
  with managed identity; `InMemoryStorage` for unit tests), `naming.py` (§20 blob names),
  `validators.py` (size, signature sniffing, executable/archive/script refusal, full Pillow decode +
  format match, pixel cap, receipt ≥ 400×300, PDF behind flag without active content, image-only
  personal photo, filename sanitizing), `services.py` (`store_document` replaces the slot under the
  application lock and removes the blob if the DB write fails; receipt → PENDING_REVIEW; deleting
  the receipt resets payment status; `document_content` audited), endpoints (upload 60/hour,
  metadata, stream or SAS redirect with `no-store`/`nosniff`/sandbox CSP, delete), `cleanup_blobs`
  (grace period, orphan blobs, dry run, idempotent via the new `blob_purged_at` column). A real
  Azurite round-trip test (`@pytest.mark.azurite`) passes.
- **Task 3.8** — OCR: `normalizers.py` (digits, first 14 digits, birth year from ID, year from any
  date format, triple name with عبد/أبو, governorate fuzzy match, enum mapping), `schemas.py`
  (Arabic prompts ported, JSON schemas for structured outputs), `OcrProvider` protocol,
  `MockOcrProvider`, `AzureOpenAIProvider` stub (refuses until Session 7), `extract_document`
  (OCR_ENABLED, ownership, capable types, PDFs skipped with a message, provider failure →
  OCR_UNAVAILABLE, audit with field names only), `POST /documents/{id}/extract/` throttled 30/hour
  per user. Nothing is saved.
- **Task 3.9** — Admin: stats, application list (filters, search by name/reference/phone/full or
  masked national ID incl. Arabic digits, ordering incl. fee total, pagination ≤ 100), detail
  (masked IDs, audited reveal, `allowed_transitions`, duplicate warnings), transition, payment
  (+ internal note), notes, audit history, doctors, fee-schedule versions
  (`fees.services.create_schedule_version`). The full 6×6 status matrix is tested through the
  admin endpoint and the doctor submit endpoint (incl. NEEDS_CORRECTION → SUBMITTED keeping the
  reference number).
- **Task 3.10** — `RequestIdMiddleware` (X-Request-ID; JSON access log with method, masked path
  without query string, status, latency, user UUID); Azure SDK logging capped at WARNING; every §39
  audit action produced by its endpoint (parametrized test) with no national ID, filename, name or
  note text in any metadata; concurrent API submissions → exactly one reference number / unique
  sequential numbers. Production settings also refuse the in-memory blob backend and mock OCR.
- **Demonstration:** `tests/test_e2e_flow.py` (pytest + Azurite) and `scripts/smoke_api.py` (real
  HTTP against `runserver`, development settings) both run dev login → profile → draft →
  beneficiaries → uploads to Azurite → OCR → fees → validation → receipt + declaration → submit →
  `MED-2026-000001`. The dev-server log contained no 14-digit run.
- **Result:** 847 tests passing on PostgreSQL 16 (was 391), `ruff check` + `ruff format --check`
  clean, `manage.py check` clean, `makemigrations --check` no changes,
  `manage.py spectacular --file openapi.yaml --validate --fail-on-warn` succeeds (30 paths), and
  `npx openapi-typescript` generates the TS types from it (not committed; Session 4).

### Session 4 — 2026-10-05 — Phase 4A (frontend foundation and shared components)
Scope limited by the user to the foundation: no doctor form, no admin pages. Built test-first
(every test file was run and seen failing before its implementation; ar.ts and config are data).
- **Toolchain:** Vite 6.4, React 19.3, TypeScript 5.9 (strict, `noUncheckedIndexedAccess`), Tailwind
  4.3 (`@tailwindcss/vite`, tokens in `src/index.css` `@theme`), React Router 7, TanStack Query 5,
  React Hook Form 7 + Zod 4 + resolvers (installed for Session 5), Vitest 4 + Testing Library + MSW 2,
  Playwright 1.63, ESLint 9 flat config. Dependency pins forced by this machine: see D56/D57.
- **Theme / RTL:** `index.html` `lang="ar" dir="rtl"`, Cairo (Google Fonts) + fallback stack, every
  §7.2 token and §7.3 status colour as Tailwind colours, paper-form tokens (`paper-line`, `ink`).
  ESLint `no-restricted-syntax` refuses physical classes in string literals and template parts
  (proved with a probe file: 5/5 violations flagged, `text-rightish` not). `rtl_check.py` vendored to
  `frontend/scripts/` (Q-T4 resolved) and passes with 0 errors / 0 warnings.
- **i18n / utils:** `src/i18n/ar.ts` holds every UI string + `t()` interpolation; enum labels come
  from reference data, not ar.ts. `utils/digits.ts` (Eastern Arabic + Persian → Western),
  `utils/format.ts` (`3٬025 ج.م`, `٣ أكتوبر ٢٠٢٦` in Cairo time, relative time).
- **API layer:** `src/api/schema.d.ts` generated from `backend/openapi.yaml` (committed, D51);
  `client.ts` (`apiFetch`: `/api/v1` prefix, JSON or multipart, `X-CSRFToken` from the cookie on
  unsafe methods, §46 envelope → `ApiError` incl. step errors, non-JSON/network failures → Arabic
  messages, 401 → `session:expired`; `apiUpload` via XHR for progress); `case.ts` camelCase ⇄
  snake_case mapping at runtime and type level (data keys such as `SON_MINOR` untouched);
  `types.ts` (generated types camelized + hand-typed reference data, fee quote, validation);
  `keys.ts`; `endpoints/{auth,reference,profile,applications,documents}.ts`.
- **Auth:** `useSession` (GET /auth/me/, `null` on 401), `RequireRole` guard (signed out → `/`, other
  role → its home), `useSignOut` (POST logout → `queryClient.clear()` → Entra logout URL or
  `/signed-out`), session-expiry listener, `DevLoginPanel` (only when `import.meta.env.DEV` and the
  backend answers; verified absent from the production bundle).
- **Routes / layouts / pages:** every §8 route in `src/router.tsx`; Public, Doctor and Admin
  (charcoal bar) layouts; LandingPage (Entra sign-in / sign-up links, `?auth_error=` messages, paper
  form header illustration, five-step explanation), SignedOutPage, NotFoundPage, DashboardPage (§43:
  greeting, cards with StatusBadge, last save, reference number, submitted date, snapshot total,
  NEEDS_CORRECTION notes + `تصحيح وإعادة التقديم`, disabled `تقديم طلب جديد` while an application is
  active, empty state, error + retry), NewApplicationPage (`/application/new` → POST → open). Other
  routes are placeholders for Sessions 5–6.
- **Shared components (§11):** `BoxInput` core + `NidInput` (14 boxes, segment gaps 1|6|2|4|1) and
  `BoxStringInput` (26 boxes, wraps), `DashedField`, `RadioBoxGroup` (real radios), `ProgressStepper`,
  `ValidationErrorPanel`, `StickyActionBar`, `StatusBadge`, `FeeSummaryPanel` (+ `useFeeQuote`),
  `SmartUpload` (upload part: pre-check from reference-data limits, upload on select with progress,
  thumbnail via `content_url`, server messages; OCR in Session 5), `DocumentModal` shell (slots from
  the server's `required_documents`), UI kit `Button`, `Icon` (`mirror` prop), `Modal` (focus trap,
  Escape, focus return), `Skeleton`, `FullPageStatus`, `UnionMark`.
- **Tests:** 137 Vitest tests in 20 files (NidInput 19, BoxStringInput 9: typing, Arabic digits,
  paste incl. `"٢٩٥٠١٢٣ ٠١٠١٢٣٤"`, Backspace, arrows, read-only, accessible names). Playwright
  `e2e/foundation.spec.ts` (desktop + 390×844): RTL + Cairo + no horizontal overflow, dev login →
  dashboard through the Vite proxy, sign-out, doctor refused from `/admin/*` — 6/6 passed.
- **Real-data check:** curl through `http://localhost:5173/api/v1` (Vite proxy → runserver): `/auth/me/`
  401 signed out, dev login 200, `/applications/` returned the doctor's FY 2026 draft (created this
  session with `POST /applications/` for `doctor@dev.local`), rendered by the dashboard in Chromium.
- **Result:** `npm run lint` clean, `npx tsc --noEmit` clean (root tsconfig is the app config; a
  planted type error is reported), `npm test` 137 passed, `npm run build` OK,
  `python frontend/scripts/rtl_check.py frontend/src` 0 errors / 0 warnings. Backend untouched
  (the 847-test suite was not re-run this session).

### Session 5 — 2026-10-06 — Phase 4B (doctor journey)
Scope limited by the user to the doctor journey (PROMPT.md §8–11, 17.6, 18, 43): no admin pages,
no profile page. Built test-first: every test file was run red before its implementation, except
`mappers.test.ts` (written first but run together with the implementation) and the PDF page-count
check (added to the e2e spec after the print view existed).
- **Backend (only change):** dev login accepts `create: true` and creates a fresh DOCTOR for an
  unknown e-mail (DEV_AUTH_ENABLED only, existing users keep their role, inactive refused) so every
  Playwright run starts without an application (D68). 4 tests; `openapi.yaml` + `schema.d.ts` regenerated.
- **Form state (§10):** `features/application-form/draftController.ts` — autosave engine outside
  React (D69): debounced 800 ms, one cycle sends only changed fields to the owning resource
  (`PATCH /profile/`, `PATCH /applications/{id}/`, `POST/PATCH /beneficiaries/`), incomplete
  national IDs/years stay local (D70), network/5xx retry 1 s/2 s/4 s then `تعذّر الحفظ — إعادة المحاولة`
  (button retries), 4xx field errors shown inline and the rest of the request re-sent (D71),
  `flush()` before continue/print/sign-out, `release()` on unmount, `beforeunload` while dirty.
  OCR merge fills only empty fields (`mergeMemberOcr`/`mergeRowOcr`, port of `handleOcrResult` /
  `updateBeneficiaryBatch`); a valid national ID pre-fills empty birth year/gender and flags a
  contradicting value (UX mirror, D72); kinship change clears that row's documents (optimistic,
  server deletes them); a cleared stored row asks before `DELETE`; read-only when not editable.
  `useApplicationDraft` + `ApplicationFormProvider` + `useApplicationForm` expose it.
- **Paper form (§9):** `PaperForm` = `FormHeader` (union, title, `أول مرة/إضافة` boxes, clickable
  112×144 photo box → PERSONAL_PHOTO) + `AttachmentsPanel` (ID front/back, syndicate card from the
  server rules, SmartUpload + `مسح تلقائي`) + `MemberSection` (7 rows, 12-col spans of §9.4, 27
  governorates, box radios, NidInput, read-only Entra e-mail boxes, LTR numeric fields) +
  `BeneficiaryTable` (exactly `max_beneficiaries` rows, fixed column layout, paperclip grey/green,
  DocumentModal with OCR into that row, confirm dialogs; cards below 768 px via `useMediaQuery`,
  table always in print) + `DeclarationSection` (exact §9.7 text, red-underlined paragraph, inline
  dashed name, signature block). `DocumentsChecklist` (step 3, member + each active beneficiary,
  ✓ مرفق / غير مرفق / اختياري, upload/replace per item), `FeeSummaryPanel` gains `title` and
  `accent` (teal start border / banana header).
- **Pages:** `WizardFrame` (sticky top bar: sign-out icon, `استمارة اشتراك — {fy}`, autosave
  indicator, print icon; sticky stepper from `steps_complete`). `FormPage` (validation panel +
  inline errors after continue, `متابعة لرفع الإيصال` → flush → fresh `GET /validation/` → steps
  1–3 clean → `/payment`, D74; read-only banner; correction notes). `PaymentPage` (§18: back link,
  banana fee summary, instructions, drop zone with type/size/400×300 pre-check, uploaded bar with
  size, payment status and `إزالة`, continue → review). `ReviewPage` (read-only sheet, server
  errors + way back, receipt hint, optimistic acceptance checkbox stored via
  `declaration_accepted`, submit/resubmit, submit errors listed). `StatusPage` (confirmation after
  submit, reference number, badge, date, snapshot total, `تم التقديم ✓ → قيد المراجعة → إشعار بالنتيجة`,
  polling 45 s while SUBMITTED/UNDER_REVIEW, notes, `تصحيح وإعادة التقديم`, print).
  `PrintPage` + `src/print.css` (A4, margin 0, exact colours, no chrome). `ApplicationRedirectPage`.
- **Fix in Session 4 code:** `BoxInput` lost a digit when several characters were inserted into a
  box holding the same leading digit (autofill/IME); it now remembers each box's selection (D80,
  two regression tests).
- **Tests:** Vitest 222 passed in 31 files (was 137): draft hook 14 (debounce, routing, OCR merge,
  ID pre-fill/mismatch, kinship change, create/delete rows, retry/backoff, error state, partial
  field errors, read-only, beforeunload), MemberSection 9, BeneficiaryTable 8, DocumentModal +1,
  DocumentsChecklist 3, SmartUpload OCR 5, FeeSummaryPanel +2, FormPage 8, PaymentPage 5,
  ReviewPage 6, StatusPage 5, Print/redirect 6, mappers 7, nationalId 3, formatFileSize 1.
- **End to end (real stack, D83):** `frontend/e2e/doctor-submit.spec.ts` — fresh doctor via dev
  login → `/application/new` → upload ID front → mock OCR fills name/ID/birth year/governorate/
  district/address → ID back + syndicate card OCR → WIFE (3 documents), SON_MINOR (birth
  certificate OCR fills name + year), DAUGHTER → fee panel `الدرجة 3`, `3٬025 ج.م` → screenshots
  1280/390 (no horizontal overflow) → continue → receipt upload → review → accept → submit →
  `MED-2026-0000NN` → print view → A4 PDF (2 pages). Artefacts in `docs/screenshots/session-5/`
  (`form-1280.png`, `form-390.png`, `status-1280.png`, `print-a4-preview.png`, `print-a4.pdf`).
- **Result:** `npm run lint` clean, `npm run typecheck` clean, `npm test` 222 passed, `npm run build`
  OK, `rtl_check.py frontend/src` 0 errors / 0 warnings, `npx playwright test` 7 passed + 1 skipped
  (the doctor spec runs on the desktop project only and resizes itself to 390 px). Backend
  `pytest` 851 passed, `ruff check` + `ruff format --check` clean.

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
- **D29 — Content sniffing with `filetype`** (pure-Python signatures) instead of python-magic
  (needs libmagic; no maintained Windows wheel), plus an executable/script/archive signature
  blocklist and a full Pillow decode whose format must match the sniffed type.
- **D30 — ID token validated independently of MSAL** with PyJWT against the tenant JWKS (MSAL does
  not verify the signature). Issuer/JWKS URI come from OIDC discovery unless `ENTRA_ISSUER` /
  `ENTRA_JWKS_URI` are set.
- **D31 — No account linking by email.** A new `(oid, tid)` whose email belongs to another account
  is refused (`EMAIL_IN_USE`); emails stay unique and takeover by email is impossible.
- **D32 — Callback failures redirect** to `/?auth_error=<CODE>` (browser navigation) instead of a
  JSON envelope; `/auth/login/` without Entra configuration is a 503 envelope `AUTH_UNAVAILABLE`.
- **D33 — Admin MFA:** with `ENTRA_ADMIN_REQUIRE_MFA` a missing `amr` claim counts as "no MFA".
- **D34 — 401 for anonymous API calls** via a SessionAuthentication subclass with a
  `WWW-Authenticate` challenge (plain DRF answers 403).
- **D35 — Dev login enforces CSRF** (login-CSRF protection), even though it is dev-only.
- **D36 — Admins do not see drafts** (list, detail, documents); review starts at SUBMITTED. Stats
  still count drafts separately.
- **D37 — Doctors never see cross-application duplicate warnings** (they would reveal that another
  member listed the same national ID); admins see them on the application detail.
- **D38 — `POST /applications/` returns the active application (200)** via the new
  `get_or_create_draft`; `create_draft` keeps raising `ACTIVE_APPLICATION_EXISTS` (D20).
- **D39 — Protected fields in a doctor payload are ignored** (every one is read-only); tests assert
  the database row is unchanged rather than expecting a 400.
- **D40 — Validation failures are 400 `VALIDATION_ERROR`** (also on submit), not 422.
- **D41 — Document content defaults to `stream`** (proxied, authorized, audited, `no-store`,
  `nosniff`, sandbox CSP); `DOCUMENT_CONTENT_DELIVERY=sas` redirects to a read-only single-blob SAS
  expiring within 300 s (TTL capped in settings and in code).
- **D42 — `Document.blob_purged_at`** (additive nullable column) makes `cleanup_blobs` idempotent.
- **D43 — Deleting the receipt resets `payment_status` to NOT_UPLOADED** (`mark_receipt_removed`).
- **D44 — PDFs (when allowed) are refused if they contain `/JavaScript`, `/JS`, `/Launch`,
  `/EmbeddedFile(s)`, `/RichMedia` or `/XFA`;** `/OpenAction` alone is allowed (scanner output).
- **D45 — OCR returns only non-empty suggestions;** fewer than 14 digits → no national-ID suggestion
  (the prototype returned a partial number); the year fallback must be 1900–2099.
- **D46 — Rate limits are DRF scoped throttles** (cache-backed): callback 20/min/IP, dev login
  30/min, uploads 60/hour/user, OCR 30/hour/user. Shared cache across replicas: Q-T6.
- **D47 — Draft-level phone:** separators/Arabic digits normalized, valid numbers stored as
  `01XXXXXXXXX`, incomplete numbers kept for autosave (rule 7 reports them at submission).
- **D48 — `User.display_name`** from the Entra `name` claim; `/auth/me/` prefers `Doctor.full_name`.
- **D49 — The profile is locked** while the current fiscal year's application is SUBMITTED,
  UNDER_REVIEW or APPROVED (409 `APPLICATION_NOT_EDITABLE`).
- **D50 — Production refuses** `BLOB_BACKEND != azure` and `OCR_ENABLED` with the mock provider;
  `API_DOCS_ENABLED` defaults to false.
- **D51 — `backend/openapi.yaml` is generated, not committed** (gitignored); Session 4 generates
  and commits `frontend/src/api/schema.d.ts`.
- **D52 — Admin payment `note` becomes an internal `AdminNote`** (`review_payment`, atomic with the
  payment change) — resolves deviation 9.
- **D53 — `allowed_transitions` hides APPROVED until payment is CONFIRMED;** the transition service
  still enforces it.
- **D54 — Development settings read the repo-root `.env`** (shared with docker compose) and default
  `BLOB_CONNECTION_STRING` to Azurite's public, documented development account on
  `AZURITE_BLOB_PORT`.
- **D55 — `rtl_check.py` is vendored** at `frontend/scripts/rtl_check.py` (copied from the `rtl-ui`
  skill, v1.0.0) so CI can run it without the plugin (Q-T4, Q-T8).
- **D56 — TypeScript 5.9**, not the current 7.x: typescript-eslint 8.71 supports `<6.1` and
  openapi-typescript 7.13 requires `^5`.
- **D57 — jsdom 26**, not 27: jsdom 27 needs `require(esm)`, unflagged only from Node 22.12; this
  machine has Node 22.11 (Q-T9).
- **D58 — Digits on screen follow PROMPT.md's examples:** money Western digits + Arabic separator
  (`3٬025 ج.م`), dates Eastern Arabic (`٣ أكتوبر ٢٠٢٦`), relative time Western (`منذ 5 دقائق`,
  §43). The rtl-ui skill advises one digit system per screen; the spec wins.
- **D59 — Enum labels only from reference data** (`statuses`, `kinships`…); `StatusBadge` takes the
  label as a prop and only owns the §7.3 colours.
- **D60 — One guard, `RequireRole`,** handles both "signed out → `/`" and "wrong role → own home".
- **D61 — `إنشاء حساب` and `تسجيل الدخول` both go to `/api/v1/auth/login/?next=/dashboard`:** Entra
  External ID's combined sign-up/sign-in user flow; the BFF has no sign-up hint (Q-B18).
- **D62 — Dashboard amounts come only from `fee_snapshot`** (submitted applications). Draft cards
  show no amount instead of one fee request per card; the form page shows the live quote.
- **D63 — `تقديم طلب جديد` navigates to `/application/new`,** which POSTs (idempotent server side,
  D38; guarded against StrictMode double effects) and replaces the URL with `/application/:id`.
- **D64 — Box inputs keep a contiguous value:** focus never lands past the first empty box,
  Backspace on a filled box removes that character (later ones shift), on an empty box it steps back
  and clears; a paste of ≥ length characters replaces the whole value. Boxes are always LTR.
- **D65 — Hand-written API shapes are `type` aliases** (interfaces have no index signature, so the
  `Camelize` mapped type cannot walk them).
- **D66 — The admin area uses a charcoal top bar**, the doctor area a white one, so a reviewer
  never mistakes which context they are in.
- **D67 — CSRF token read from the `csrftoken` cookie on every unsafe request;** the `csrf_token`
  in the `/auth/me/` body is not used.
- **D68 — `POST /auth/dev/login/ {"email", "create": true}`** creates a DOCTOR for an unknown
  e-mail (dev/test only, 404 otherwise). Chosen over the plan's `?reset=1` because it deletes
  nothing (the audit log is append-only and protects users).
- **D69 — The autosave engine is a plain class** (`DraftController`) read through
  `useSyncExternalStore`: the React Compiler lint rules forbid refs/setState during render and in
  effects, and timers/in-flight requests must not depend on render timing. Timings live in
  `draftDefaults` (tests shorten them).
- **D70 — Incomplete national IDs (< 14 digits) and years (< 4 digits) are never sent** while
  drafting; they stay local (dirty → `beforeunload` warns) until complete or cleared (`null`).
- **D71 — Save failures:** network/5xx → automatic retries 1 s, 2 s, 4 s, then the indicator turns
  into a retry button; 4xx → the field messages are shown under their fields and the same request is
  re-sent without the refused fields so the rest is saved. A field stays dirty until the server
  acknowledged that exact value.
- **D72 — Frontend national-ID parsing is a UX mirror** (century, real past date, position 13
  parity) for pre-filling empty birth year/gender and an early mismatch hint; PROMPT.md §13 allows
  it. The server re-parses on PATCH and in validation.
- **D73 — Wizard steps (form, payment, review) and the print view sit outside `DoctorLayout`:** they
  render `WizardFrame` (the §9.1 top bar + stepper) or no chrome (print); status stays in the
  doctor layout.
- **D74 — `متابعة لرفع الإيصال` is gated by step 1–3 errors only.** The declaration-name error
  (step 5) shows inline after continuing and blocks on the review page.
- **D75 — The review page lists the validation endpoint's errors;** rules 16–17 (receipt,
  acceptance) are not in that response (D24), so the page shows a receipt hint from
  `steps_complete["4"]` and lists the submit endpoint's step errors when a submission is refused.
- **D76 — Row documents are read from the application query, not kept in form state;** a kinship
  change empties that row's cached documents immediately and the PATCH response confirms it.
  Opening the paperclip of a row not yet stored flushes the autosave first (the upload needs the
  beneficiary id).
- **D77 — Status polling every 45 s** only while SUBMITTED or UNDER_REVIEW; the timeline marks
  step 2 current for both and fills step 3 with the decision (approved / rejected / correction).
- **D78 — The acceptance checkbox is optimistic** (follows the click, reverts if the PATCH fails);
  submit stays disabled until the server stored the acceptance.
- **D79 — One beneficiaries layout is rendered at a time** (`useMediaQuery("(min-width: 768px)")`,
  desktop when `matchMedia` is missing), so inputs are never duplicated in the DOM.
- **D80 — `BoxInput` remembers each box's selection** (`select`, `mouseup`, `keyup`) to tell a
  replacement from an insertion before/after the existing character when a change carries several
  characters.
- **D81 — Payment instructions are static text in `ar.ts`** until the organization provides them
  (§18 says admin-configurable; see Q-B19).
- **D82 — The e2e run gives its doctor a random valid national ID** after OCR: the mock provider
  always returns `28506150101234`, and `Doctor.national_id` is UNIQUE across runs.
- **D83 — Session evidence (screenshots + A4 PDF) is committed** under `docs/screenshots/session-5/`;
  it contains only synthetic data and `e2e-*@dev.local` addresses.

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
| 11 | plan: commit after every task | one commit `Phase 3B: API, auth, documents, OCR` | explicit user instruction |
| 12 | plan 3.5 `test_submit_errors_422_...` | 400 `VALIDATION_ERROR` | D40: one status for every validation failure |
| 13 | plan 3.3 callback error "returns envelope" | 302 to `/?auth_error=<CODE>` | D32: the browser is navigating |
| 14 | §23 / plan 3.7 python-magic | `filetype` + signature blocklist + Pillow decode | D29 |
| 15 | plan 3.6 beneficiary response includes `warnings` | omitted for doctors, shown to admins | D37: privacy |
| 16 | plan 3.8 throttle inside the OCR service | DRF scoped throttle on the view | standard DRF mechanism, per user |
| 17 | plan 3.4 reference-data keys `document_types`, `member_documents`, `beneficiary_document_rules` | one `document_rules` key = `rules_as_reference_data()` | the rules table is described in exactly one place |
| 18 | plan "curl smoke through compose" | `scripts/smoke_api.py` against `runserver` + `tests/test_e2e_flow.py` | compose has no Django service until Session 6 |
| 19 | plan 3.7 `BlobStorage` protocol | adds `list(prefix)` | needed by the orphan-blob cleanup |
| 20 | plan 4.1 `tailwind.config.ts`, `.eslintrc` | Tailwind 4 `@theme` in `src/index.css`; ESLint 9 flat `eslint.config.js` | current major versions have no JS config / legacy rc |
| 21 | plan 4.1 `gen:api` from `../backend/schema.yml` | `../backend/openapi.yaml` | the file name chosen in Session 3 (D51) |
| 22 | plan 4.3 `RequireAuth.tsx` + `RequireRole.tsx` | `RequireRole.tsx` only | D60 |
| 23 | plan: commit after every task; "Session 4: frontend foundation" | one commit `Phase 4A: frontend foundation` | explicit user instruction |
| 24 | plan 4.4 `Badge`, `Card`, `Table`, `Toast`, `ConfirmDialog` | not built yet | user scope for 4A lists §11 components; built with their first use (ConfirmDialog for kinship change in Session 5) |
| 25 | plan 4.5 `AutosaveIndicator` | not built (strings in ar.ts) | belongs with autosave in Session 5 |
| 26 | plan 4.6 `rtl:check` → plugin path | vendored script (D55) | runnable in CI |
| 27 | plan "dev login works to an empty dashboard placeholder" | real dashboard with API data | user's scope for this session |
| 28 | plan Session 5 owns SmartUpload, DocumentModal, FeeSummaryPanel | built now (upload part / shell / panel) | user's scope for this session; OCR, checklist and modal wiring stay in Session 5 |
| 29 | plan 6.4 Playwright doctor flow | only `e2e/foundation.spec.ts` now | the doctor flow does not exist yet |
| 30 | plan 5.1 `BeneficiaryRow.documents` in form state, `useApplicationDraft` holding the logic | documents read from the application query; logic in `draftController.ts` | D69, D76 |
| 31 | plan 5.2 `useUploadDocument`/`useExtract`/`DocumentThumb`/`preCheck` as separate files | OCR mutation inside `SmartUpload`; `useUploadDocument` for compact slots (photo, checklist); thumbnail inline | fewer files, same behaviour |
| 32 | plan 5.6 `ProfilePage` | `/profile` still a placeholder | user scope for this session; the form edits the profile fields |
| 33 | plan 6.4 (Session 6) Playwright doctor spec with `?reset=1` | built now; `create: true` dev login | user asked for it in Session 5; D68 |
| 34 | user: "add WIFE and SON_MINOR" | WIFE, SON_MINOR **and DAUGHTER** | worked example 2 (§17.4/§42) totals 3025 only with the daughter |
| 35 | §18 instructions "configurable by admins" | static placeholder text | D81, Q-B19 |
| 36 | plan "commit `Session 5: doctor flow`" | one commit `Phase 4B: doctor flow` | explicit user instruction |
| 37 | plan Session 5 "manual run through compose" | Playwright run against `runserver` + Vite + compose (PostgreSQL, Azurite) | compose has no Django service until Session 6 |

## Open questions

Business questions 1–14 are tracked in `docs/business-rules.md` §10 (defaults implemented, to be
confirmed by the organization). Technical/environment questions for the user:

- **Q-T1** Azure subscription, region and Entra External ID tenant are not available in this session;
  Sessions 7–8 will generate everything and mark Azure-dependent checks `NOT VERIFIED — requires Azure credentials`.
- **Q-T2** Resolved: Docker Desktop 29.7.2 runs PostgreSQL 16 + Azurite.
- **Q-T3** Resolved: Python 3.12.15 (uv, D10); Node v22.11.0 / npm 11.7 are installed.
- **Q-T5** CI and Azure must use PostgreSQL ≥ 15 (`NULLS NOT DISTINCT`, D17); Bicep should pin 16.
- **Q-B15** (business) Confirm the Arabic payment-status labels (D26) and whether an admin may change
  a payment decision after APPROVED (currently refused).
- **Q-T4** Resolved: `rtl_check.py` vendored to `frontend/scripts/` (D55).
- **Q-T8** The `rtl` plugin directory ships no LICENSE file. Confirm redistributing the vendored
  `rtl_check.py` in this repository is acceptable, or replace it with a download step in CI.
- **Q-T9** This machine runs Node 22.11. Upgrading to the current 22.x LTS (≥ 22.12) lets jsdom 27
  be used (D57); CI (Session 8) should pin the latest 22.x.
- **Q-T10** Cairo is loaded from Google Fonts. The Static Web Apps CSP (Session 8) must allow
  `fonts.googleapis.com` / `fonts.gstatic.com`, or the font is self-hosted (the rtl-ui skill's
  recommendation; also removes a third-party request).
- **Q-B18** (business) Should `إنشاء حساب` open Entra's sign-up page directly? That needs the BFF to
  forward a sign-up hint (`prompt=create`); today both buttons use the combined flow (D61).
- **Q-T6** Throttle counters use the default cache (local memory per replica). With several Container
  App replicas the effective limit multiplies; Session 6/7 must set `CACHE_URL` to a shared cache
  (Azure Cache for Redis, or `dbcache://django_cache` + `createcachetable` in the migration job).
- **Q-T7** Entra External ID is NOT VERIFIED against a real tenant. The tenant must emit the `email`
  claim (optional claim) and, for admin MFA enforcement, `amr`; otherwise set
  `ENTRA_ADMIN_REQUIRE_MFA=false` and rely on Conditional Access (Session 7/8 docs).
- **Q-B16** (business) Should admins see drafts before submission? Default: no (D36).
- **Q-B17** (business) The receipt minimum is applied as width ≥ 400 AND height ≥ 300 (prototype
  rule), so a portrait 300×400 photo is refused. Confirm, or relax to "either orientation".
- **Q-B19** (business) The payment instructions on the receipt page are placeholder text (D81).
  The organization must provide the real text (bank / branch / e-payment details); deciding whether
  admins edit it in the UI adds a settings model in a later session.
- **Q-T11** The e-mail row of the paper form has 26 boxes; longer Entra e-mails are shown with as
  many boxes as needed (wrapping), never truncated. Confirm this is acceptable on the printed form.

## Next session starts with

**Session 6 — Admin UI + local end-to-end environment** (`docs/plan.md` → Session 6). The doctor
journey is complete; Task 6.4 (doctor Playwright spec) is already done (deviation 33).
1. Environment: Docker Desktop must be running → `docker compose up -d`; in `backend/`:
   `DJANGO_SETTINGS_MODULE=config.settings.development .venv/Scripts/python manage.py runserver 8000`;
   in `frontend/`: `npm ci && npm run dev`. Checks: `npm run lint`, `npm run typecheck`, `npm test`
   (expect **222 passed**), `npm run build`, `python scripts/rtl_check.py src`,
   `npx playwright test` (expect 7 passed, 1 skipped; each doctor run creates one `e2e-*@dev.local`
   doctor and one submitted application with a new reference number). Backend: 851 passed.
2. Reuse for the admin pages: `PaperForm` (wrap in `ApplicationFormProvider readOnly`) for the
   admin detail/print views needs an admin data source — the draft hook reads the doctor
   endpoints (`/applications/{id}/`, `/profile/`), so the admin print page should get its own
   read-only provider fed from `GET /admin/applications/{id}/` (or `submitted_snapshot`).
   `StatusBadge`, `StatusTimeline`, `FeeSummaryPanel`, `ConfirmDialog`, `useMediaQuery`,
   `formatFileSize`, `DocumentModal` (read-only) are ready.
3. Carry-over: `/profile` page (deviation 32), admin print route, Q-B19 payment instructions.
4. Testing notes: `src/test/renderForm.tsx` renders inside a live provider; `draftDefaults` shortens
   autosave timings in page tests; `vi.mock("@/features/documents/imageSize")` for receipt sizes;
   `e2e/make-fixtures.py` regenerates the synthetic upload images.
