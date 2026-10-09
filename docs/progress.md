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

### Session 6 — 2026-10-06 — Phase 4C (admin UI) + Phase 5 (local environment)
Scope set by the user: admin pages (§8, §44), Django in docker compose with seed and §32 scripts,
frontend ⇄ backend verified end to end. Built test-first: every new test file was run red before
its implementation (admin pages: 33 failing tests first; seed: 5 failing; dev-login race: 1).
- **Admin API layer:** `src/api/endpoints/admin.ts` (stats, list with every §24 filter, detail with
  `reveal_national_id`, transition, payment, notes, audit, doctors, fee schedules — tier/fee keys
  such as `grad_son` are never camelized), admin types in `types.ts`, `queryKeys.admin`,
  `features/admin/queries.ts` (one action refreshes detail, revealed variant, audit, lists, stats).
- **Pages (§8, §44):** `AdminDashboardPage` (seven §44 tiles, each a link to the filtered list),
  `AdminApplicationsPage` (URL-driven search/filters/ordering/pagination, sortable headers with
  `aria-sort`, cards below 768 px), `AdminApplicationDetailPage` (member data, masked national ID +
  audited "show full", application data, member documents, beneficiaries with required/missing
  documents, `DocumentViewer` modal via `content_url`, fee SNAPSHOT, duplicate warnings,
  `TransitionButtons` from the server's `allowed_transitions`, `ActionDialog` with required notes for
  correction/rejection and the server's Arabic refusal in place, `PaymentPanel` confirm/reject with
  optional internal note, doctor-visible review notes, `NotesPanel`, `AuditList` with Arabic action
  names and status/payment arrows, print link), `AdminPrintPage` (same A4 `PaperForm` fed from the
  admin endpoint via `DraftPreset`, masked unless revealed), `AdminDoctorsPage` / `AdminDoctorDetailPage`,
  `AdminFeeSchedulesPage` (versions, read-only tier table with ranges from the schedule's boundaries,
  settings, new-version form prefilled from the shown version, Arabic digits accepted, confirmation
  dialog, success message). Admin routes are lazy chunks (main bundle 530 → 483 kB, no Vite warning).
- **Local environment (§32):** `backend/Dockerfile` (`dev` stage: python 3.12-slim, uid 1000,
  healthcheck on `/api/ready/`), `backend/entrypoint.sh` (waits for the database, migrates when
  `RUN_MIGRATIONS_ON_START`, seeds when `SEED_ON_START`), `backend/.dockerignore`, compose `backend`
  service (development settings, dev auth, mock OCR, Azurite by service name, source bind-mounted,
  `depends_on` healthy). `seed_dev_data` rewritten: FY 2026 schedule ensured, admin, `doctor@`
  (worked example 2, SUBMITTED, receipt pending, 3025), `doctor2@` (female + MOTHER, UNDER_REVIEW →
  NEEDS_CORRECTION by the admin with notes, 2075), `new.doctor@` (empty) — all through the domain
  services with real actors and real Azurite blobs; idempotent. Root `package.json` scripts and a
  `Makefile` (up, down, logs, migrate, makemigrations, seed, test, lint, dev, e2e, ci).
  `docs/local-development.md` rewritten.
- **Bugs found and fixed:** (1) `.gitignore` `reference/` also ignored `backend/apps/reference/` and
  `frontend/src/features/reference/` — 17 core files (national ID, document rules, constants,
  reference-data API, `useReferenceData`) had **never been committed**; anchored to `/reference/`
  and committed now (found because ruff in the container, without `.git`, linted files the host
  skipped). (2) Dev login `create` raced on the unique e-mail under parallel Playwright workers →
  500; now handles `IntegrityError` (regression test). (3) The e2e dev-login helper raced the SPA's
  own `/auth/me/` for the `csrftoken` cookie → intermittent CSRF 403; it now waits for that request.
  (4) The production-settings test inherited the container's `OCR_*` environment; isolated.
  (6) Found by the post-commit security review: route params were interpolated into API paths, and
  React Router decodes `%2F`, so a crafted link (`/admin/applications/..%2F..%2Fauth%2Flogout`)
  could aim a CSRF-bearing request at another same-origin endpoint (also true of the Session 4–5
  doctor endpoints). `buildUrl` now refuses any path segment outside `[A-Za-z0-9_-]` before a
  request is built (D99); 9 tests (8 client, 1 page). Frontend total 269.
  (5) Two lint findings in the previously hidden files (unused `noqa`, yoda comparison) + format.
- **Verification (outputs in the session transcript):** fresh stack on empty volumes
  (`docker compose -p medical-fresh up -d`, alternate ports): postgres, azurite, backend healthy,
  all migrations applied, seed printed `MED-2026-000001 SUBMITTED` / `MED-2026-000002
  NEEDS_CORRECTION`, `/api/ready/` 200, a seeded document streamed as PNG from Azurite; then
  `down -v`. `npm run dev` (port 5174, because a Vite server started before this session holds
  5173) served `<html lang="ar" dir="rtl">` and proxied `/api/ready/` 200 and `/api/v1/auth/me/` 401
  to the container.
- **Tests:** backend **855 passed** on the host and inside the container (`npm run test:backend`,
  Azurite tests included; was 851), ruff check + format clean in both. Frontend `npm run ci` green:
  ESLint, `tsc` (app + node/e2e), Vitest **260 passed in 38 files** (was 222), `rtl_check` 0/0,
  build. Playwright **9 passed, 3 skipped** (mobile duplicates of the self-resizing specs), green
  three runs in a row: `admin-approve.spec.ts` (dashboard tiles → filtered list → sort → search →
  detail → receipt viewer → approve hidden until payment confirmed → confirm payment → start
  review → approve → audit shows both arrows → 390 px no overflow on list and detail → doctor sees
  `تم قبول الطلب` and the note), `correction-loop.spec.ts` (notes required → correction → doctor
  sees the note on the dashboard → fixes the neighbourhood → payment → review → resubmit → same
  reference number → admin sees مقدم + `إعادة تقديم الطلب` in the audit), plus the Session 4/5 specs.
  Screenshots in `docs/screenshots/session-6/`.

### Session 7 — 2026-10-06 — Phase 6 (Azure integration + production Docker image)
Scope set by the user: Blob via managed identity (Azurite locally), Key Vault settings, Entra-token
PostgreSQL backend, Azure OpenAI OCR provider, Application Insights with masking, production
Dockerfile + entrypoint without migrations, `production.py` hardening and startup checks. No Azure
resource was created and nothing was deployed. Built test-first: every new test module was run red
(6 collection errors) before its implementation.
- **Shared credential** `config/azure.py`: one cached `DefaultAzureCredential`
  (`managed_identity_client_id` from `AZURE_CLIENT_ID`) used by Blob, Key Vault, PostgreSQL, Azure
  OpenAI and Application Insights (one token cache) — D100.
- **Blob (Task 7.1)** `apps/documents/storage.py`: connection string wins (Azurite), otherwise
  account URL + the shared credential; user-delegation key cached for 1 h and renewed before a
  5-minute SAS could outlive it; SAS read-only, one blob, ≤ 300 s (D101).
- **Key Vault (Task 7.2)** `config/secrets.py::load_secrets(names, vault_url, required)`: env wins,
  then `KEY_VAULT_URL` with the managed identity; `ENTRA_CLIENT_SECRET` ↔ `entra-client-secret`;
  vault errors become `ImproperlyConfigured` naming the secret, never its value (D102).
- **PostgreSQL (Task 7.3)** `config/db/entra_postgres/base.py`: `DatabaseWrapper` puts an Entra
  access token (`https://ossrdbms-aad.database.windows.net/.default`) in the password of every new
  connection, cached until 5 min before expiry, refuses non-TLS `sslmode`; production
  `DB_AUTH_MODE=entra` (default) selects it and caps `CONN_MAX_AGE` at 1800 s;
  `DB_AUTH_MODE=password` keeps the stock backend with `DATABASE_PASSWORD` (env / Key Vault) or the
  URL password (D103).
- **OCR (Task 7.4)** `apps/ocr/providers/azure_openai.py`: `openai.AzureOpenAI` with
  `get_bearer_token_provider(credential, cognitiveservices scope)` (no API key), one
  `chat.completions.create` with the Arabic system instructions + the §21.3 prompt from
  `schemas.py`, the image as a `data:` URL, strict `json_schema` response format, `store=False`,
  30 s timeout, 1 retry; refusals, truncation, invalid JSON and every SDK/credential error become
  `OcrProviderError` with no chained exception (D104). `docs/ocr.md` written.
- **Telemetry (Task 7.5)** `config/telemetry.py`: `configure_telemetry()` in `wsgi.py` before
  Django loads (per Gunicorn worker), no-op without `APPLICATIONINSIGHTS_CONNECTION_STRING`;
  `MaskingSpanProcessor` (span names, attributes, exception events) and
  `MaskingLogRecordProcessor` (bodies, attributes incl. stack traces) registered before the
  exporters; `TelemetryLogHandler` attached to the root logger through Django `LOGGING` with the
  `mask_national_ids` filter (D105); psycopg 3 instrumented explicitly (the distro only knows
  psycopg2); optional Entra ingestion (`APPLICATIONINSIGHTS_AUTHENTICATION=entra`).
- **Production settings (Task 7.5, §30)**: Key Vault secrets; required `CSRF_TRUSTED_ORIGINS`,
  `ENTRA_AUTHORITY/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI`; TLS-only `DB_SSLMODE`; Blob account keys
  refused (managed identity only, Azurite string allowed for local runs, D106); Azure OpenAI
  settings required when OCR uses it; HSTS preload on (D107); COOP; API CSP middleware;
  `HealthProbeMiddleware` first in `MIDDLEWARE` (all settings) so probes bypass host validation and
  the HTTPS redirect (D108); `DEV_AUTH_ENABLED` / `DEBUG` refusals kept.
- **Docker (Task 7.6)** `backend/Dockerfile`: `builder` (wheels) → `runtime` (python:3.12-slim,
  wheels bind-mounted so they are not a layer, uid 10001 `app`, code owned by root,
  `collectstatic` at build with base settings, Python `HEALTHCHECK` on `/api/health/`,
  `ENTRYPOINT entrypoint.sh`, `CMD web`) and the unchanged `dev` stage. `entrypoint.sh` modes:
  `web` (Gunicorn, refuses `RUN_MIGRATIONS_ON_START=true`), `migrate` (waits for the database, then
  `migrate --noinput`: the Container Apps job), `cleanup` (`cleanup_blobs` + args), anything else
  runs as before (compose dev). `config/gunicorn.py`: workers/threads/timeout from env, no preload,
  **access log off** (query strings may hold a national ID; Django writes the masked access log),
  control socket off (D109).
- **Local TLS for PostgreSQL**: `backend/scripts/local_postgres_tls.py` issues a self-signed cert
  with `cryptography` and enables `ssl=on` in the compose PostgreSQL through `docker exec` (the
  alpine image has no `openssl`), so the production image runs locally with `sslmode=require`
  (D110). Development settings (`sslmode=prefer`) keep working.
- **Dependencies:** `azure-keyvault-secrets` 4.11, `openai` 3.24 (`httpx2` transport),
  `azure-monitor-opentelemetry` 1.8.10 + `opentelemetry-instrumentation-psycopg` 0.65b0 (pinned
  together), Gunicorn 26.2. The host venv had no pip: bootstrapped with `ensurepip` (uv is not on
  PATH in this shell).
- **Docs:** `docs/ocr.md`, `docs/security.md` (draft: controls + legal decisions L1–L8),
  `.env.example` gained every new name.
- **Verification (outputs in the session transcript):**
  - `docker build --target runtime -t medical-backend:runtime backend/` succeeded (432 MB).
  - Run on the compose network with `config.settings.production`, `DB_AUTH_MODE=password`,
    `DB_SSLMODE=require`, the Azurite connection string, placeholder Entra values and a random
    secret: container `healthy`, `whoami` → `app` (uid 10001); `GET /api/health/` 200
    `{"status": "ok"}`; `GET /api/ready/` 200 `{"database": "ok"}` with the connection on TLSv1.3
    (`pg_stat_ssl`); probe with `Host: 10.0.0.12:8000` 200; API over plain HTTP → 301 to https;
    via `X-Forwarded-Proto: https` → 401 with CSP, HSTS (1 year, preload), nosniff,
    `Referrer-Policy: same-origin`, COOP, `X-Frame-Options: DENY`, `X-Request-ID`; unknown Host →
    400; storage = `AzureBlobStorage` reaching Azurite; `migrate` mode → "No migrations to apply";
    `cleanup --dry-run` → `purged=0 orphans=0`; `web` + `RUN_MIGRATIONS_ON_START=true` → exit 1;
    `DEV_AUTH_ENABLED=true` → `ImproperlyConfigured: DEV_AUTH_ENABLED must never be enabled in
    production.`
  - `python manage.py check --deploy` with production settings (host, both `DB_AUTH_MODE`s, and
    inside the image): **System check identified no issues (0 silenced)** — nothing to justify.
  - Backend **940 passed** in the compose container (`npm run test:backend`, Azurite tests
    included; was 855), 939 on the host + the Gunicorn test; ruff check + format clean.
    Frontend `npm run ci` green (**269 passed**, unchanged code). Playwright **9 passed, 3 skipped** against the rebuilt stack (PostgreSQL with TLS on).
  - **Fixed after the post-commit security review:** the span processor only masked 14+ digit
    runs, so full request URLs (`url.full`/`http.url`/`http.target`/`url.query`) would have sent
    admin search terms (names, 11-digit phones, e-mails) and the Entra callback's `code`/`state`
    to Application Insights. URL attributes now keep scheme/host/path only, `url.query` is
    dropped, and credential headers (cookie, set-cookie, authorization, CSRF) are dropped if
    header capture is ever enabled (D112). Backend 942 passed.
  - **NOT VERIFIED — requires Azure credentials:** managed-identity tokens; Blob access and
    user-delegation keys on a real account (roles Storage Blob Data Contributor + Storage Blob
    Delegator); Key Vault reads (Key Vault Secrets User); Entra login to Azure Database for
    PostgreSQL (identity mapped to a role); Azure OpenAI calls (Cognitive Services OpenAI User,
    model quality, content filtering on ID documents); Application Insights export and Entra
    ingestion (Monitoring Metrics Publisher); probe/Host/`X-Forwarded-Proto` behaviour behind
    Container Apps ingress and the SWA linked backend.

### Session 8 — 2026-10-06 — Phase 7 (infrastructure) + Phase 8 (CI/CD)
Scope set by the user: modular Bicep (§33), Entra / PostgreSQL / GitHub OIDC scripts, GitHub
Actions (§36), `docs/entra-setup.md`, `docs/github-setup.md`. Nothing was deployed to Azure, no
repository was created, nothing was pushed. Skills: `azure-prepare` (design + plan in the
gitignored `.azure/deployment-plan.md`), `entra-app-registration`, `azure-validate` (core checks,
static role review), Azure MCP Bicep schemas / best practices / retail prices.
- **Bicep** `infrastructure/main.bicep` (resource-group scope) + 14 modules: `identity`,
  `monitoring`, `key-vault` (RBAC, soft delete, purge protection, audit logs), `storage` (private
  `medical-documents`, no public access, **shared keys disabled**, TLS 1.2, soft delete, versioning,
  lifecycle for previous versions), `postgres` (Flexible Server 16, Entra auth, password auth off by
  default, TLS >= 1.2 enforced, PITR/geo-backup/HA parameters, Azure-services-only firewall or VNet
  integration, optional Entra admin), `container-registry`, `container-apps-env` (workload
  profiles, Log Analytics), `container-app` (app + manual `migrate` job + scheduled `cleanup` job,
  Key Vault references through the user-assigned identity, startup/liveness `/api/health/`,
  readiness `/api/ready/`, HTTP-concurrency scaling, single-revision mode), `static-web-app`
  (Standard, PR previews disabled), `static-web-app-link` (linked backend, D115), `openai`
  (conditional, keys disabled, vision deployment), `role-assignments` (7 roles, each on one
  resource), `network` + `private-endpoints` (behind `enablePrivateNetworking`). Names from
  `uniqueString(resourceGroup().id, environment, baseName)`, tags on everything, all sizes are
  parameters; `parameters/{dev,staging,prod}.bicepparam` read tenant/principal ids and the image
  from environment variables (nothing environment-specific committed). Two-phase first deployment
  (D113). Strict `infrastructure/bicepconfig.json` (secret/unused-param rules as errors, recent API
  versions as warnings); API versions refreshed to current GA from the linter's list.
- **Scripts** `infrastructure/scripts/`: `create-entra-app.sh/.ps1` (web platform, implicit flow
  off, openid/profile/email, `email` optional claim, callback + `/signed-out` redirect URIs,
  user-flow link, client secret straight into Key Vault with an expiry, never printed, rotation
  with `--append`), `setup-postgres-entra.sh` (Entra admin, database owned by it, identity role via
  `pgaadauth_create_principal_with_oid`, least-privilege grants, temporary firewall rule removed
  on exit), `setup-github-oidc.sh/.ps1` (deployer identity per environment, federated credential
  `repo:<owner>/<repo>:environment:<env>`, Contributor + AcrPush + RBAC Administrator restricted by
  an ABAC condition to the template's roles, D118). All idempotent; nothing embeds an ID.
- **Workflows** `.github/workflows/`: `frontend.yml` (§36 chain, one build promoted dev -> staging ->
  prod), `backend.yml` (ruff, `check`, migrations check, OpenAPI validation, pytest on `postgres:16`,
  runtime image built once + non-root / refusal checks, promoted per environment),
  `infrastructure.yml` (build + lint + script checks, what-if on PR, what-if + deploy on main, manual
  dispatch), `e2e.yml` (fresh compose stack, Azurite pytest, Playwright), three `reusable-*.yml`
  deploy workflows. Backend deploy = push -> migrate job update + start + wait -> cleanup job image ->
  new revision -> wait Healthy -> smoke test. OIDC only; the SWA deployment token is read at run time
  and masked (D116); every action pinned to a commit SHA resolved with `git ls-remote` (D117).
- **Application changes:** `backend/entrypoint.sh` `migrate` mode also runs `createcachetable` so
  `CACHE_URL=dbcache://django_cache` gives every replica one throttle store (Q-T6, D114; red -> green
  shown in the compose container, then in the production image over TLS).
  `frontend/public/staticwebapp.config.json` (SPA fallback excluding `/api/*`, strict CSP allowing
  only Google Fonts, HSTS, nosniff, DENY, COOP, Permissions-Policy, caching) +
  `src/staticWebAppConfig.test.ts` (7 tests, red first).
- **Docs:** `docs/entra-setup.md`, `docs/github-setup.md`, `docs/azure-deployment.md` (two-phase
  commands, migrations + rollback, backups/restore + RPO/RTO + drill, private-networking upgrade,
  cost table from the Azure Retail Prices API, troubleshooting), `docs/security.md` §5.1.
- **Verification (outputs in the session transcript):**
  - `az bicep build` main + 14 modules: all exit 0, **0 warnings** under the strict config;
    `az bicep lint` all clean; `az bicep build-params` dev/staging/prod OK; parameter behaviour
    checked (no `CONTAINER_IMAGE` -> `deployApplication=false`; with it -> `true`).
  - `az deployment group what-if` / `validate`: **NOT VERIFIED — requires Azure credentials.** The
    signed-in "Azure for Students" subscription answers `ReadOnlyDisabledSubscription`
    (azure-validate `validate-deployment.sh`: CLI PASS, auth PASS, compile PASS, validate/what-if
    FAIL for that reason only). Its policy allows only five regions without Static Web Apps (Q-T15).
  - **actionlint 1.7.12** (Docker, with shellcheck 0.11 on every `run:` block): 0 errors in 7 files.
    **shellcheck** on the three scripts + `entrypoint.sh`: clean; `bash -n` OK; PowerShell 5.1 parser:
    0 errors in both `.ps1`. `setup-postgres-entra.sh` SQL run against the compose PostgreSQL 16
    (database/role names with spaces and dashes, idempotent re-run, grants checked).
  - **gitleaks 8.30.1**: full history (10 commits) **no leaks**; staged changes: 2 findings, both
    public built-in role GUIDs (Key Vault Secrets User/Officer) -> annotated `gitleaks:allow`,
    re-scan **no leaks**.
  - CSP: production build served with the exact `globalHeaders` + `/api` proxy, Chromium
    (Playwright MCP): landing, doctor form with three thumbnails, admin detail, admin image viewer —
    no CSP violation; Cairo loaded from Google Fonts.
  - Backend **942 passed** (compose), ruff check + format clean; frontend `npm run ci` green
    (**276 passed**, was 269); `docker build --target runtime` OK; production image `migrate` mode
    with production settings over TLS: migrations + cache table, idempotent.
- **Fixed after the post-commit security review (2 findings, both accepted):** (1) CI/CD trust — the
  pull-request what-if ran in the unprotected `dev` environment with the deploy identity, so a PR
  branch could edit the workflow and deploy; now PRs and what-if-only runs use `<env>-plan`
  (read + what-if only) and `dev`/`staging`/`prod` accept `main` only (D126). (2) Over-broad grant —
  the RBAC-admin condition limited the roles but not the principal, so the deployer could grant
  itself Blob/Key Vault data access; the condition now also pins the app identity's principal id
  and Key Vault Secrets Officer left the list (D118). Scripts, workflows and docs updated;
  re-verified with bash -n, shellcheck, the PowerShell parser, actionlint and gitleaks.
- **Second review round (over-broad grant / CI trust in `setup-github-oidc`), accepted:** Contributor
  could add a federated credential to the app identity (sign in as the app) and list storage keys;
  the deploy identity's trust depended on a GitHub setting nobody checked. Now a custom *Deployer*
  role (Contributor minus federated-credential writes and storage key/SAS listing) replaces
  Contributor (an old Contributor assignment is removed), and the script verifies the GitHub
  environment's branch policy / prod reviewers with `gh api` before trusting the deploy identity
  (fails closed; `--skip-github-check` warns) (D127).

### Session 9 — 2026-10-06 — Phase 9 (full testing + security review)
Scope set by the user: run every check, prove each PROMPT.md §2.3 requirement with a test, a
strict security review, fix rather than list. Every fix was test-first (red shown, then green).
Full record: `docs/verification.md`; review: `docs/security.md` §8.
- **Task 9.1 — e2e:** `admin-approve` / `correction-loop` already existed (Session 6). New:
  `print-a4.spec.ts` (worst case: 10 beneficiaries with long names and national IDs, doctor and
  admin print views, PDF page tree parsed and cross-checked, nothing wider than A4, no clipped
  input, no validation marks → 2 pages each) and `mobile-form.spec.ts` (real Pixel 7 profile at
  390 × 844 with touch: dashboard → card layout → beneficiary + document → Eastern Arabic year →
  fee 2٬475 → receipt → review → submit; no horizontal scroll on any page). The e2e helper now
  builds drafts from the server's own `required_documents` (`createDraftApplication`).
- **Defects found by the new specs:** (V1) printed beneficiary names and the declared name were
  clipped by their inputs → print-only wrapping copies (D128); (V2) the admin's masked national ID
  printed with the red "14 digits" hint → client ID hints only on editable forms (D129).
- **Task 9.2 — verification:** backend **960 passed** (was 942; pytest 9.1.1), ruff clean,
  `check` clean, no missing migrations, 26 migrations on a new empty database (idempotent);
  frontend `npm run ci` green (**281 passed**, was 276; rtl 0/0; build with 0 source maps);
  Playwright **11 passed / 5 skipped** twice in a row; production image `--no-cache` build,
  healthy against compose PostgreSQL (TLS) + Azurite, headers/redirect/Host checks live;
  `check --deploy` **with exactly the main.bicep environment** → no issues (found V3 = F7 on the
  way); Bicep main + 14 modules + 3 param files, 0 warnings; actionlint 0; gitleaks history clean;
  pip-audit (prod + the image's frozen 77 packages) and npm audit clean; dev pytest CVE fixed.
- **§2.3 requirement map** (12 defects → tests) in `docs/verification.md` §2; two missing proofs
  added: `test_extract_only_suggests_and_saves_nothing` (mutation-checked red) and the Bicep
  template guard.
- **Task 9.3 — security review (manual; the `security-review` skill needs a git remote):** F1 XFF
  throttle bypass + spoofable audit IP (D130), F2 admin MFA bypass through `grant_admin` mid-session
  (D131), F3 upload size checked only after spooling the whole body (D132), F4 expired sessions
  never purged (D135), F5 = Q-T17 PDF viewer could never render (D133), F6 production source maps
  (D134), F7 Key Vault read of an unused DB password at every start (D136), F8 dev pytest CVE.
  `infrastructure/scripts/check-template-security.py` + CI step (D137).
- **NOT VERIFIED — requires Azure credentials:** unchanged list from Sessions 7–8, plus the
  `TRUSTED_PROXY_COUNT=2` assumption (Q-T13) and ingress/SWA body-size limits.

### Session 10 — 2026-10-06 — Phase 10 (deployment readiness: documentation + final report)
Scope set by the user: Phase 10 only; no behaviour change unless a document revealed a real bug.
- **README.md** written (§50): ASCII architecture, layout, local setup, every environment variable
  explained, migrations, seeding, tests, Docker, Azure prerequisites, Entra, two-phase
  infrastructure deployment, application deployment, OCR, admin grant, troubleshooting — Bash and
  Windows PowerShell where they differ. Every code block parses (`bash -n` 10/10, PowerShell
  parser 7/7); the PowerShell fresh-stack + `grant_admin` commands were run on a throwaway
  compose project.
- **docs/** (§51): `database.md` written from the migrated database (Mermaid ER, constraints,
  indexes, JSON columns, migrations); `architecture.md` corrected (400 not 422, MVP network
  posture, data-model summary, new scaling section, pipeline); `azure-deployment.md` gained
  step-by-step restore procedures A–D, RPO/RTO table and the quarterly drill (§48), an initial
  production configuration and a cost-driver table (§52); `security.md` §0 maps every §47
  control to its implementation and lists the decisions needing legal approval; stale "Session
  N / planned" wording fixed in `security.md`, `github-setup.md`, `ocr.md`, `api.md`;
  `business-rules.md` §10 row 8 corrected (there is no `PAYMENT_INSTRUCTIONS` setting) and
  questions 15–21 added; PowerShell variants in `local-development.md`.
- **Bug found by the documentation review (fixed test-first, D139):** `.env.example` says "copy to
  `.env`", but development settings loaded empty values too → host-run Django crashed
  (`int('')`) and `DEV_AUTH_ENABLED`/`OCR_ENABLED` would have turned false. Reproduced against the
  real settings, red test, then `config/envfile.py::read_env_file`.
- **Spec gap found and reported, not changed:** React Hook Form / Zod are installed but unused
  (deviation 66).
- **Verification:** backend **964 passed, 1 skipped**; frontend **281 passed**, rtl 0/0, build OK;
  Playwright **11 passed / 5 skipped**; runtime image built; `check --deploy` with the Bicep
  environment clean; Bicep + params build, guard 0 problems / self-test 20/20; gitleaks clean.
  Screenshots under `docs/screenshots/` were regenerated by the e2e run.
- **docs/final-report.md** (§56, all 15 items).

### Session 11 — 2026-10-07 — First Azure deployment, dev phase 1
Scope set by the user: dev only, resource group `Medical_App` (uaenorth), repo
`amr990719/Medical_App_Azure` (already pushed, **public**; visibility left unchanged).
- **Tooling:** az 2.88.0, Bicep 0.48.1, gh 2.102.0 (signed in as `amr990719`), Docker 29.7.2,
  Node 22.11.0 / npm 11.7.0. **Not installed:** `psql` (needed for `setup-postgres-entra.sh`) and
  PowerShell 7 (Windows PowerShell 5.1 is used).
- **Azure:** subscription "Azure subscription 1" (`247d882f-…`, Pay-As-You-Go, no spending limit),
  tenant "Default Directory" (`448ad25b-…`), no policy assignments. Registered the eleven resource
  providers (none were registered).
- **GitHub environments** created: `dev`, `staging` (protected branches only), `prod` (protected
  branches only + required reviewer `amr990719`, D141), `dev-plan`, `staging-plan`, `prod-plan`.
  `main` is **not** branch-protected yet, so no workflow can deploy to `dev` until it is.
- **OIDC (`setup-github-oidc`, dev):** created `id-medsyn-dev`, `id-github-medsyn-dev`,
  `id-github-medsyn-dev-plan`, federated credentials, custom roles `Deployer (Medical_App)` and
  `Deployment What-If Operator (Medical_App)` and their assignments. Two script bugs found and
  fixed (commit `30d6489`): wrong AcrPush role id in both scripts (`…-7f3ba6c4aaa5` →
  `…-304f252e45ec`; Azure returned `RoleDefinitionDoesNotExist`) and `Test-Az` aborting under
  Windows PowerShell 5.1 (`2>$null` + `ErrorActionPreference=Stop`). The PowerShell script then
  ran to completion. The bash script on Git Bash additionally needs `MSYS_NO_PATHCONV=1` and a
  Windows-readable `TMPDIR` (not changed in the script).
- **GitHub variables** on `dev` and `dev-plan`: `AZURE_CLIENT_ID` (deploy / plan identity),
  `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP=Medical_App`,
  `STATIC_WEB_APP_LOCATION=eastasia`.
- **Bicep phase 1** (`main-dev`, no `CONTAINER_IMAGE`): what-if showed creates only (no deletes),
  deployment **Succeeded** in 6 min 14 s. `westeurope` refused the Static Web App ("not accepting
  new customers"), so it is in `eastasia` (D140). Outputs: Key Vault `kvmedsyndevyoepoxdsywea2`,
  ACR `crmedsyndevyoepoxdsywea2`, PostgreSQL `psql-medsyn-dev-yoepoxdsywea2`, identity
  `id-medsyn-dev`, Static Web App `swa-medsyn-dev-yoepoxdsywea2` /
  `victorious-meadow-0e5775b00.4.azurestaticapps.net`, storage `stmedsyndevyoepoxdsywea2`.
- **Key Vault:** `django-secret-key` generated locally and set through a temp file (never printed).
- **PostgreSQL (`setup-postgres-entra.sh`):** you are the Entra admin; database `medical` and the
  `id-medsyn-dev` role with least-privilege grants created; the temporary firewall rule was removed.
  Script fix (commit `e8836c2`): az 2.88 firewall-rule arguments are `--server-name` / `--name`.
- **Entra External ID:** tenant "Medical Syndicates Project" (`medicalsyndicates.onmicrosoft.com`,
  id `24135332-2a51-43e7-ae99-8b85467b7002`), user flow `signup-signin` (`22bf7bf2-…`, created
  by the user, **Arabic not enabled yet**). `create-entra-app.ps1` created `medical-syndicates-dev`
  (client id `f4bac467-5e63-47a2-8eb6-aceb55725824`), linked it to the flow and stored
  `entra-client-secret` in Key Vault (expires 2027-10-07). `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`,
  `ENTRA_AUTHORITY` set on GitHub `dev`. Script fix: Graph permissions are now set as a complete
  list (`permission add` appended duplicates on every re-run); re-run verified (3 permissions,
  1 secret). Sign-in notes: the workforce tenant's security defaults refused Key Vault tokens
  (`AADSTS530035`) after a device-code sign-in; `az login --tenant <workforce> --scope
  https://vault.azure.net/.default` fixed it.

### Session 12 — 2026-10-08 — dev phase 2 (backend Container App + frontend)
Scope set by the user: `docs/deployment-path.md` §11–12 for dev. Arabic on the user flow was
not part of it and is still open.
- **Image:** built locally from `runtime`, but it could not be pushed from this machine.
  `az acr login` failed with `AADSTS530035`, even right after a fresh MFA sign-in (the ARM token
  had `amr=pwd,mfa`; the CLI's ACR token path is refused for the live.com guest account). A manual
  `/oauth2/exchange` login worked, but `docker push` timed out on the ~90 MB dependency layer
  three times (connections to uaenorth kept resetting). Built in the registry instead with
  `az acr run` (D142); the quick build (`az acr build`) fails because it uses the legacy builder,
  which rejects `RUN --mount`.
- **Bicep phase 2** (`main-dev`, `CONTAINER_IMAGE` set; `KEY_VAULT_OPERATOR_*` taken from the
  phase-1 deployment parameters, `ENTRA_*` from GitHub `dev`, PostgreSQL admin variables left empty
  as in phase 1): what-if showed 4 creates (Container App `ca-medsyn-dev-api`, jobs
  `caj-medsyn-dev-migrate` / `caj-medsyn-dev-cleanup`, SWA linked backend `django-api`). The rest
  was read-only-property noise and no deletes. Succeeded in 4 min 48 s.
- **Bug found in Azure, fixed test-first (`35770c4`):** the revision never became ready. Every
  startup probe got 400 `DisallowedHost: 'localhost:8000'` because the OpenTelemetry Django
  instrumentation (active only with an App Insights connection string, so never in tests) inserts
  its middleware at index 0, in front of `HealthProbeMiddleware`, and calls
  `build_absolute_uri()`. `configure_telemetry()` now defaults
  `OTEL_PYTHON_DJANGO_MIDDLEWARE_POSITION=1`; a regression test instruments Django for real and
  probes with `Host: localhost:8000` under strict `ALLOWED_HOSTS`. Suite: 966 passed, 1 skipped
  (container); ruff clean. Host-run pytest currently fails on this machine (the compose PostgreSQL
  rejects the `medical` password from the host); the container path is unaffected.
- **Redeployed** with image `35770c4…` (ACR run `dg5`): revision `ca-medsyn-dev-api--0000001`
  Running / Healthy. **Migrate job** succeeded twice (`…-87cwgyq` on the first image, `…-krlhord`
  on the fixed one).
- **Frontend:** `npm ci && npm run build` (typecheck included), deployed with SWA CLI 2 to
  `swa-medsyn-dev-yoepoxdsywea2` (token passed through `SWA_CLI_DEPLOYMENT_TOKEN`, never printed).
- **Verified through `https://victorious-meadow-0e5775b00.4.azurestaticapps.net`:** `/` 200
  (`<html lang="ar" dir="rtl">`, Arabic title), deep link `/doctor/form` 200 (SPA fallback),
  `/api/health/` 200, **`/api/ready/` 200 `{"status": "ok", "database": "ok"}`** (Entra token auth
  to PostgreSQL works), `/api/v1/reference-data/` and `/auth/me/` return the §46
  `NOT_AUTHENTICATED` envelope, and `/api/v1/auth/login/` redirects with 302 to
  `medicalsyndicates.ciamlogin.com/…/authorize` with the right client id and redirect URI. The
  Container App FQDN answers 401 to everything, as expected: the link enables `azureStaticWebApps`
  auth on it. **Not verified:** an interactive sign-in, blob upload, App Insights ingestion.
- **Docs:** `deployment-path.md` §11 readiness now goes through the SWA host (the old FQDN check
  can only return 401), adds a troubleshooting snippet and the `az acr run` fallback, and §19 has
  four new rows.
- **GitHub (after the deploy):** `dev` now has `ACR_NAME`, `CONTAINER_APP_NAME`, `MIGRATE_JOB_NAME`,
  `CLEANUP_JOB_NAME`, `STATIC_WEB_APP_NAME`; `dev-plan` got `CONTAINER_APP_NAME` + the three
  `ENTRA_*` values (the PR what-if keeps the running image only with them). `main` is protected
  (D143). Remote `main` is still `5092034 first commit`; the 7 local commits since then are not
  pushed, and no workflow has ever run, so no status-check names exist yet.
- **First real sign-in → second Azure-only bug, fixed test-first (`8490e3a`):** every
  `/auth/callback/` logged `ID token rejected, reason: nonce`, so no user was created and
  `grant_admin amr_ashraf55@hotmail.com` failed with "No single user matches". MSAL keeps the raw
  nonce in the flow but sends `sha256(nonce)` hex to the authority, while `validate_id_token`
  compared the claim with the raw value. The test fake used `"nonce-1"` on both sides. Now
  `nonce_claim()` hashes the flow nonce, the fake follows MSAL's contract, a token with the raw
  nonce is rejected, and a contract test drives MSAL's real `initiate_auth_code_flow`. Suite:
  968 passed, 1 skipped; ruff clean. Image `8490e3a…` (ACR run `dg6`) deployed: revision
  `ca-medsyn-dev-api--0000002` Healthy, `/api/ready/` 200 (no migrations in this change).
- **One-off management commands** in Azure: `az containerapp exec` needs a TTY, so the job's
  full container (image, 31 env vars, secrets) is copied from `GET …/jobs/caj-medsyn-dev-migrate`
  and posted to `…/start` with only `args` replaced (`--image` overrides on `job start` may drop the
  env). Output: `az containerapp job logs show` (needs the `containerapp` extension, 1.3.0b5 installed).
  Log Analytics queries are refused by security defaults (non-ARM token).
- **First real sign-in verified** (after `8490e3a`): `/auth/callback/` 302 created user
  `c1b0d7b9-…`, `/auth/me/` 200, sign-out then sign-in again matched the same user by (oid, tid).
  `grant_admin amr_ashraf55@hotmail.com` ran as job execution `caj-medsyn-dev-migrate-myfcr7j`:
  "Granted ADMIN to user c1b0d7b9-…". Admin sign-in with MFA is **not verified** yet.
- **First CI run (PR #1, branch `deploy/dev-phase-2`):** backend tests, frontend CI, Playwright and
  the image build passed. Two infrastructure failures, both fixed:
  (1) shellcheck SC2015 in `setup-postgres-entra.sh` (`5e2f05b`);
  (2) the dev-plan what-if failed with `AADSTS700213`. The repository uses **immutable OIDC
  subjects** (`repo:amr990719@202661413/Medical_App_Azure@1408726581:environment:…`), but
  `setup-github-oidc` had created the classic `repo:amr990719/Medical_App_Azure:…` subjects. Both
  scripts now read `sub_claim_prefix` from the GitHub API, and both dev federated credentials were
  updated. Re-running the PowerShell script also found that the custom-role update path (never
  exercised before) died on an az stderr warning under 5.1 (fixed: `Continue` for that call), and
  that it needs a Graph token, which security defaults refuse for this account. So `dev-plan` was
  updated directly with `az identity federated-credential update`; the roles were unchanged.
- **Azure CLI sessions last about an hour:** with security defaults and a personal (live.com)
  account, the CLI cannot refresh tokens silently, so long sessions need repeated MFA `az login`.

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

- **D84 — Transition buttons come from the server's `allowed_transitions`;** the SPA keeps no copy
  of the transition table (plan 6.1 suggested a UI mirror). The only UI rule is the hint "confirm
  the payment before approving" while UNDER_REVIEW without a confirmed payment.
- **D85 — The admin list state lives in the URL** (`status`, `payment_status`, `fiscal_year`,
  `governorate`, `syndicate_type`, `sub_syndicate`, `submitted_from/to`, `search`, `ordering`,
  `page`); any change other than the page returns to page 1; search runs on submit (Enter/button),
  Arabic digits normalized first. Dashboard tiles link to these URLs.
- **D86 — "Show full national ID" is a separate query variant** (`masked` / `revealed` cache keys);
  each reveal is one audited `reveal_national_id=1` request, hiding switches back to the masked
  cache. The admin print page is masked by default with the same audited toggle.
- **D87 — The admin print view reuses `PaperForm`** through `DraftPreset` (admin detail mapped to
  the doctor `Application` + `DoctorProfile` shapes, always read-only, provider keyed by the reveal
  state) instead of a second print layout.
- **D88 — Payment buttons** appear only while SUBMITTED / UNDER_REVIEW / NEEDS_CORRECTION and a
  receipt exists (mirror of D23 for UX; the server decides); the button matching the current
  payment status is hidden. A note typed in the dialog becomes an internal note (D52).
- **D89 — Audit action names are UI strings in `ar.ts`** (`admin.audit.actions`); the audit enum is
  admin-only display text and is not part of `/reference-data/`.
- **D90 — Fee schedule versions are never editable in the UI** (immutable, D14); "new version" is a
  form prefilled from the version on screen, integers only (Arabic digits accepted), confirmed in a
  dialog, then audited by the server (`FEE_SCHEDULE_CHANGED`).
- **D91 — Admin routes are lazy-loaded** (React Router `lazy`): doctors never download the review UI.
- **D92 — Compose reaches Azurite by service name** (`AZURITE_BLOB_HOST=azurite`, port 10000, new
  development setting) instead of `UseDevelopmentStorage=true`, which the SDK hard-wires to
  `127.0.0.1:10000` (unreachable from a container).
- **D93 — The compose backend migrates and seeds on start** (`RUN_MIGRATIONS_ON_START`,
  `SEED_ON_START`, both `true` only in the `dev` image/compose). The production stage (Session 7)
  must default both to false (§37).
- **D94 — `seed_dev_data` drives the domain services with real actors** (doctor uploads and
  submits, admin transitions), so seeded applications have real blobs, snapshots, reference
  numbers and a realistic audit trail. The FY 2026 amounts are read from the fees seed migration
  (one definition).
- **D95 — Both a root `package.json` and a `Makefile`** expose the §32 commands; this machine has no
  `make`, so the npm scripts are the verified path. `test:backend` forces `--ds=config.settings.test`
  (pytest-django lets `DJANGO_SETTINGS_MODULE` override the ini).
- **D96 — Admin e2e specs create their submitted application through the doctor API**
  (`e2e/helpers.ts::createSubmittedApplication`) — repeatable and independent of the seed; the doctor
  UI path is covered by `doctor-submit.spec.ts`. E-mails carry a random suffix (parallel workers can
  share a millisecond).
- **D97 — Dev login `create` is race-safe:** an `IntegrityError` on the unique e-mail signs in as the
  user the concurrent request created.
- **D98 — `.gitignore` ignores `/reference/` (root only);** the unanchored rule hid two source
  directories since Session 1.
- **D99 — API paths are allowlisted centrally:** every segment must match `[A-Za-z0-9_-]*`
  (literal names and UUIDs only); anything else is a local `NOT_FOUND` (`العنصر المطلوب غير موجود.`)
  and no request is sent. One check in `buildUrl` covers `apiFetch` and `apiUpload`.

- **D100 — One process-wide Azure credential** (`config/azure.py`), read from the environment
  (not Django settings) because the Key Vault loader runs while settings are imported.
  `AZURE_TOKEN_CREDENTIALS=prod` is an environment setting for Azure (Session 8), not code.
- **D101 — User-delegation key cached per storage client for 1 h**, renewed when a new SAS
  (≤ 5 min) could outlive it; account-key signing kept only for Azurite.
- **D102 — Key Vault is a fallback, the environment wins.** Container Apps Key Vault references
  are the primary path (§29); `KEY_VAULT_URL` covers names not injected. A missing secret is
  skipped; a required one missing everywhere refuses startup.
- **D103 — `DB_AUTH_MODE` defaults to `entra` in production.** `CONN_MAX_AGE` capped at 1800 s
  (an open connection stays valid after its token expires, but new connections always get a fresh
  token); TLS enforced both in settings and in the backend.
- **D104 — OCR provider errors carry no cause.** `raise … from None` drops SDK exceptions, which
  can contain request/response content; the client is cached per endpoint/API version.
- **D105 — Telemetry log handler lives in Django `LOGGING`.** Django's `dictConfig` would remove a
  handler the distro attached to the root logger, so the distro's handler is parked on
  `config.telemetry.distro` and ours (with the masking filter) is configured by production
  settings when a connection string exists. Span masking rewrites the finished span in a
  processor registered before the batch exporter (relies on SDK private attributes; pinned by a
  test with the real SDK).
- **D106 — Blob account keys are refused in production;** only the Azurite well-known account may
  use a connection string (local production-like runs).
- **D107 — `SECURE_HSTS_PRELOAD=True` by default** (plan 7.5); env can turn it off. The header
  alone does nothing until the domain is submitted to the preload list (organizational decision).
- **D108 — Probes bypass host validation:** `HealthProbeMiddleware` (first) answers
  `GET /api/health/` and `/api/ready/` before `CommonMiddleware`/`SecurityMiddleware`, because
  Container Apps probes use the replica IP as Host and plain HTTP. They are no longer
  access-logged.
- **D109 — Gunicorn access log off, control socket off;** Django's masked access log is the only
  one.
- **D110 — Local TLS via a script, not a compose change:** enabling TLS on the existing volume is
  reversible (`ALTER SYSTEM RESET ssl`) and needs no new image.
- **D111 — `collectstatic` at build time uses `config.settings.base`** with a throwaway build-only
  key; no secret enters the image. Static files are not served (JSON API only).

- **D112 — Telemetry never exports query strings or credential headers,** matching the access
  log; only the path of a URL leaves the process.

- **D113 — Two-phase first deployment:** Container Apps resolve Key Vault references when the app
  is created, so `deployApplication=false` (derived from an empty `CONTAINER_IMAGE`) creates
  everything else first; secrets, Entra app and PostgreSQL role are set; the second phase creates
  the app, jobs and SWA link. Infrastructure redeploys pass the running image so they never roll
  the application back.
- **D114 — Shared throttle cache = PostgreSQL `DatabaseCache`** (`dbcache://django_cache`, table
  created by the migrate job) instead of Azure Cache for Redis: no extra resource or cost; the
  throttle write rate (auth callback, uploads, OCR) is low.
- **D115 — SWA linked backend in its own module** (`static-web-app-link.bicep`): the Container App
  needs the Static Web App hostname (CSRF origin, redirect URI) and the link needs the app id, so
  one module would be circular.
- **D116 — No GitHub secrets at all:** every Azure value is a GitHub environment *variable*; the
  Static Web Apps deployment token is read with OIDC at run time and masked.
- **D117 — Actions pinned to commit SHAs** (tag in a comment), resolved with `git ls-remote` because
  the GitHub MCP server failed to connect; inputs checked against each `action.yml` at that SHA.
- **D118 — Deployer least privilege:** Contributor + AcrPush on the environment's resource group
  and *Role Based Access Control Administrator* with an ABAC condition limited to the six app role
  definitions **and to the app identity's principal id** (pre-created by `setup-github-oidc`), so
  the deployer cannot grant itself or another principal data access (no Owner / User Access
  Administrator). `KEY_VAULT_OPERATOR_*` is therefore only used by human deployments.
- **D126 — Two GitHub trust levels per environment** (post-commit security review): `<env>` is
  restricted to the protected `main` branch (reviewers for prod) and holds the deploy identity;
  `<env>-plan` holds a Reader + custom what-if identity and is the only one pull requests and
  what-if-only runs reach (on `pull_request` the PR branch controls the workflow files).
- **D127 — Custom Deployer role instead of Contributor** for the GitHub deploy identity (no
  `federatedIdentityCredentials` writes, no storage key/SAS listing), and `setup-github-oidc` fails
  closed unless the GitHub deploy environment is restricted to protected branches. NOT VERIFIED that
  every Bicep resource deploys with it (the excluded actions are not used by the template).
- **D119 — PostgreSQL database created by the Entra admin (script), not Bicep,** so it is owned by
  an Entra principal that can grant on schema `public`; the app identity is a non-admin role with
  `CONNECT/CREATE/TEMP` + `USAGE/CREATE` on `public` (the migrate job owns the tables).
- **D120 — Storage shared-key access disabled** (`allowSharedKeyAccess=false`): the app only uses
  the managed identity and user-delegation SAS (D106), so account keys are unusable even if leaked.
- **D121 — Container Apps workload-profiles environment (Consumption profile):** required for
  VNet integration with a /27+ subnet and the current default; scale-to-zero in dev only.
- **D122 — Image built once per commit and promoted** as a workflow artifact (`docker save`) to
  each environment's own registry, keeping registries/identities separate (§49) without rebuilds.
- **D123 — Infrastructure what-if on pull requests runs against dev only** (with the `dev-plan`
  identity, D126); staging/prod print their what-if inside the deploy job (prod after the required
  approval); a manual dispatch with `what_if_only=true` previews any environment via `<env>-plan`.
- **D124 — Static Web App headers** (`staticwebapp.config.json`): CSP `default-src 'self'`, no inline
  or eval script, Google Fonts as the only external origin (Q-T10), `frame-ancestors 'none'`;
  PR preview environments disabled because they would share the linked backend.
- **D125 — Application Insights Entra-only ingestion** (`DisableLocalAuth`) in staging/prod; the
  connection string is still provided (it identifies the resource); dev keeps local auth (Q-T14).

- **D128 — Paper print shows values as text:** the beneficiary name and the declared name print
  from a print-only element that wraps; the `<input>` is hidden in print (an input clips silently).
- **D129 — National-ID consistency hints only while editable:** read-only sheets (status, print,
  admin) get none; the admin copy holds a masked value.
- **D130 — Client address = the trusted proxies' X-Forwarded-For entry:** `TRUSTED_PROXY_COUNT`
  feeds DRF `NUM_PROXIES` (0 in base settings: header ignored; 2 in production and Bicep: SWA
  linked backend + Container Apps ingress); `apps/common/client_ip.py` gives the audit hash the
  same address. Never the whole header (DRF's default when `NUM_PROXIES` is None).
- **D131 — Session bound to the role:** `User.get_session_auth_hash` mixes in `role`; any role
  change ends that user's sessions (and this release signs everyone out once).
- **D132 — Request body cap before parsing:** `RequestBodyLimitMiddleware` answers 413
  `FILE_TOO_LARGE` when `Content-Length` > `MAX_UPLOAD_BYTES` + `MULTIPART_OVERHEAD_BYTES` (256 KB).
- **D133 — Only JPEG/PNG/WebP are shown inline;** every other document type is delivered as an
  attachment (stream and SAS) and the admin viewer offers a download. Nothing is framed; SWA
  `frame-src 'none'` (resolves Q-T17).
- **D134 — No source maps in production builds** (`build.sourcemap = false`).
- **D135 — The cleanup job also runs `clearsessions`** (skipped with `--dry-run`).
- **D136 — `DATABASE_PASSWORD` is requested from Key Vault only when `DB_AUTH_MODE=password`.**
- **D137 — Template security guard in CI:** stdlib Python over the compiled `main.json`, with a
  self-test that breaks each rule; complements (does not replace) Azure Policy.
- **D138 — e2e drafts follow the server's rules:** `createDraftApplication` uploads exactly the
  `required_documents` the API returns for each beneficiary (no rules table in the tests).
- **D139 — The local `.env` loader skips empty values** (`config/envfile.py`), and the real
  environment always wins; a verbatim copy of `.env.example` keeps every default.
- **D140 — dev Static Web App in `eastasia`** (user's choice): `westeurope` refused new SWA
  customers for this subscription; eastasia is the closest allowed region to the uaenorth backend.
  The SWA region is fixed at creation; `/api` traffic transits it (legal decision L3 still open).
- **D141 — `prod` reviewer is the single maintainer, self-review allowed:** with one person on the
  repository, `prevent_self_review: true` (docs/github-setup.md §2) would make prod undeployable.
  Turn it on once a second reviewer exists.
- **D142 — Manual dev images are built in the registry** (`az acr run` with a BuildKit task file,
  from a `git archive` of `backend/` at HEAD, tagged with the commit SHA) whenever pushing from a
  workstation fails. The output matches `docker build --target runtime` and pins the image to a
  commit. CI (`backend.yml`) still builds and pushes from the runner.
- **D143 — `main` protection for a single maintainer** (user's choice): pull request required with
  0 approvals, stale reviews dismissed, conversations resolved, no force pushes, no deletion,
  enforced for admins too. Required status checks are not set yet: no workflow has run, and every
  workflow is path-filtered, so a required check from a skipped workflow would block unrelated PRs
  forever. Add them through an always-running gate job, or by choosing checks carefully. Replaces
  the "1 approval" rule in deployment-path.md §4.3 while there is one maintainer.
- **D145 — No PR what-if; no `-plan` environments** (user's choice): the dev-plan what-if failed
  with `AuthorizationFailed` for every resource in the template. ARM what-if preflight needs
  write permission on each resource (20 refusals: storage, Key Vault, identities, nested
  deployments), not only `deployments/whatIf/action`, so a read-only preview identity cannot work.
  PRs now get no Azure credential (`bicep build` + lint only); what-if runs inside each deploy job
  and in manual runs from `main`, both in the branch-protected `<env>`. The `id-github-medsyn-dev-plan`
  identity, its role and the `dev-plan` GitHub environment are unused; deleting them is left to the
  user (destructive).
- **D144 — Admin MFA on dev is enforced by Conditional Access only** (user's choice):
  `entraAdminRequireMfa = false` in `dev.bicepparam`. Microsoft documents `amr` as v1.0-only, and
  External ID issues v2.0 ID tokens, so the app-side check (`"mfa" in amr`) refused an admin who
  had just completed email-OTP MFA (`MFA_REQUIRED`). The tenant's CA policy must cover every admin.
  Staging and prod still say `true` and would lock admins out the same way: decide before they
  exist (options: the same choice, or a CA authentication context checked via the `acrs` claim).

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
| 38 | plan 6.1 `allowedTransitions(status, paymentStatus)` UI helper mirroring the table | server `allowed_transitions` only | D84: server authoritative, no duplicated table |
| 39 | plan 6.1 files `useAdminStats/…/RevealNationalId.tsx`, `TransitionButtons` tests | hooks in `features/admin/queries.ts`; reveal inside the detail page; extra `ActionDialog`, `PaymentBadge`, `Pagination`, `SearchBox`, `toDraftPreset` | fewer files, same behaviour; all tested through the pages |
| 40 | plan 6.3 `BLOB_CONNECTION_STRING=UseDevelopmentStorage=true` | `AZURITE_BLOB_HOST=azurite` + port | D92 |
| 41 | plan 6.2 test "locked versions are read-only" | no version is editable at all; locked versions carry a badge | D90 / D14: versions are immutable |
| 42 | user: "two doctors with applications" | two doctors with applications **plus** `new.doctor@` without one | keeps the first-sign-in experience (Session 3 seed) |
| 43 | D59 "enum labels only from reference data" | audit action labels in `ar.ts` | D89 |
| 44 | §8 every page responsive | applications list switches to cards below 768 px; doctors, beneficiaries and fee tables scroll horizontally inside their own container | wide tabular data; the page itself never scrolls sideways (checked at 390 px for list and detail) |
| 45 | plan: commit per task, "Session 6: admin ui and local e2e" | one commit `Phase 4C-5: admin UI and local environment` | explicit user instruction |
| 46 | plan Session 6 "Task 6.4 Playwright doctor flow" | already done in Session 5; this session adds the §42 admin and correction-loop specs (plan 9.1) | user scope for this session |
| 47 | plan 7.4 PDF first page via `pypdfium2` | PDFs keep the clear `OCR_UNAVAILABLE` message | §21.2 allows "skip OCR for PDFs with a clear message"; PDF uploads are off by default |
| 48 | plan 7.5 `DATA_UPLOAD_MAX_MEMORY_SIZE` 9 MB | 2 MB (non-file bodies); files streamed above 2 MB, capped by `MAX_UPLOAD_BYTES` | stricter; the 9 MB figure only matters if files were held in memory |
| 49 | plan 7.6 `HEALTHCHECK CMD curl …`, `libmagic1` | Python `urllib` health check, no apt packages | no curl/libmagic needed (`filetype`, D29); smaller image |
| 50 | plan 7.6 `gunicorn … --access-logfile -` | access log off | D109: Gunicorn's lines include query strings |
| 51 | plan 7.3 path `backend/config/db/entra_postgres/base.py` with the token in the backend only | same path; `CONN_MAX_AGE` cap and TLS rule also in `production.py` | misconfiguration fails at startup, not on the first connection |
| 52 | plan: commit `Session 7: azure integration and production image` | `Phase 6: Azure integration` | explicit user instruction |
| 53 | plan 7.6 verify `docker run … manage.py check` | full run: container healthy against compose PostgreSQL (TLS) + Azurite, job modes, refusals | user's done-when |
| 54 | plan 8.2 `grant-github-oidc.sh` | `setup-github-oidc.sh` + `.ps1` | explicit user instruction ("section 36.1" — PROMPT.md has no §36.1; §36 + plan 8.4 used) |
| 55 | §33 module list | extra modules `static-web-app-link.bicep` (D115), `network.bicep` + `private-endpoints.bicep` (`enablePrivateNetworking`) | circular dependency; §34 upgrade path |
| 56 | plan 8.1 PostgreSQL database in Bicep (implied) | database + identity role created by `setup-postgres-entra.sh` | D119 |
| 57 | plan 8.3 secret `SWA_DEPLOYMENT_TOKEN` | not used; token read over OIDC at run time | D116 |
| 58 | plan 8.3 what-if on PR | dev only on PR | D123 |
| 59 | plan: commits per task, `Session 8: infrastructure and ci/cd` | one commit `Phase 7-8: infrastructure and CI/CD` | explicit user instruction |
| 60 | plan 8.1 roles list | + Storage Blob Delegator (account) + Monitoring Metrics Publisher | user-delegation SAS (D101) and Entra telemetry ingestion need them |
| 61 | plan 9.1 page count with `pdf-lib` | page tree parsed from the PDF (`/Count` cross-checked with the page objects) | no new dependency |
| 62 | plan: commits per task + `Session 9: testing and security review` | one commit `Phase 9: verification and security fixes` | explicit user instruction |
| 63 | plan 9.3 `security-review` skill | manual review with the same scope | the skill needs a git remote (none, by design) |
| 64 | §44 document viewer shows every document | images shown; PDF/HEIC offered as a download | D133 (security: no uploaded file is framed) |
| 65 | §55 "README contains deployment commands" | done in Session 10 | — |
| 66 | §6 / §41 React Hook Form + Zod for instant validation | installed, not used: custom form controller; instant feedback = server `/validation/` after each autosave + local hints | the server is authoritative either way; reported in `docs/final-report.md` §13 (adopt or remove the dependencies) |
| 67 | plan Task 10.1/10.2: two commits (`docs: readme and documentation set`, `Session 10: documentation and final report`) | one commit `Phase 10: deployment readiness` | explicit user instruction |

## Open questions

- **Q-D1 — Concurrent dev deploys on merge:** `infrastructure.yml` and `backend.yml` both run
  on a push to `main`. The infrastructure run reads the "running image" before its Bicep
  deployment and re-applies it, so it can roll back an image `backend.yml` deployed in between.
  Check the active revision's image after merges that touch both; long term, serialize them (for
  example, make backend wait for infrastructure, or have Bicep read the image at deploy time).

Business questions 1–14 are tracked in `docs/business-rules.md` §10 (defaults implemented, to be
confirmed by the organization). Technical/environment questions for the user:

- **Q-T1** Azure subscription, region and Entra External ID tenant are still not available; Session 7
  code paths are mocked and marked `NOT VERIFIED — requires Azure credentials` (list in Session 7).
- **Q-T2** Resolved: Docker Desktop 29.7.2 runs PostgreSQL 16 + Azurite.
- **Q-T3** Resolved: Python 3.12.15 (uv, D10); Node v22.11.0 / npm 11.7 are installed.
- **Q-T5** CI and Azure must use PostgreSQL ≥ 15 (`NULLS NOT DISTINCT`, D17); Bicep should pin 16.
- **Q-B15** (business) Confirm the Arabic payment-status labels (D26) and whether an admin may change
  a payment decision after APPROVED (currently refused).
- **Q-T4** Resolved: `rtl_check.py` vendored to `frontend/scripts/` (D55).
- **Q-T8** The `rtl` plugin directory ships no LICENSE file. Confirm redistributing the vendored
  `rtl_check.py` in this repository is acceptable, or replace it with a download step in CI.
- **Q-T9** This machine runs Node 22.11. Upgrading to the current 22.x LTS (≥ 22.12) lets jsdom 27
  be used (D57). CI uses `node-version: "22"` (latest 22.x).
- **Q-T10** Resolved for now: the Static Web Apps CSP allows `fonts.googleapis.com` /
  `fonts.gstatic.com` (checked in Chromium). Self-hosting Cairo would remove the third-party request
  (rtl-ui skill recommendation) — optional.
- **Q-B18** (business) Should `إنشاء حساب` open Entra's sign-up page directly? That needs the BFF to
  forward a sign-up hint (`prompt=create`); today both buttons use the combined flow (D61).
- **Q-T6** Resolved (Session 8, D114): `CACHE_URL=dbcache://django_cache`, table created by the
  migrate job.
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

- **Q-B20** (business) Printed admin copies show the national ID masked unless the reviewer
  reveals it (audited). Confirm whether official printouts must always carry the full ID.
- **Q-B21** (business) A payment decision stays as it was when a correction is requested and the
  doctor resubmits (a CONFIRMED payment stays confirmed unless the doctor replaces the receipt,
  which resets it to PENDING_REVIEW). Confirm this is the intended policy.
- **Q-T12** Locally the dev database still accumulates `e2e-*@dev.local` data (`docker compose down
  -v` resets it); `e2e.yml` runs on a fresh stack every time.
- **Q-T13** Container Apps ingress / SWA linked backend: confirm the `Host` header Django sees,
  that `X-Forwarded-Proto: https` is set (ALLOWED_HOSTS, HTTPS redirect, CSRF origin), that each
  hop appends exactly one `X-Forwarded-For` entry (`TRUSTED_PROXY_COUNT=2`, D130) and the request
  body limits of both hops. NOT VERIFIED — requires Azure credentials.
- **Q-T14** Application Insights ingestion: connection string only, or Entra-authenticated
  (`APPLICATIONINSIGHTS_AUTHENTICATION=entra` + `Monitoring Metrics Publisher`, local auth disabled
  on the resource)? Default here: connection string; recommended: Entra.
- **Q-B22** (business/legal) Decisions L1–L8 in `docs/security.md` §6 (religion field, OCR by an AI
  service, region / cross-border transfer, retention, admin access, breach procedure, production
  access, malware scanning).
- **Q-T15** The available "Azure for Students" subscription is disabled (read-only) and its policy
  allows only `switzerlandnorth`, `germanywestcentral`, `francecentral`, `polandcentral`,
  `italynorth` — Static Web Apps is offered in none of them. Production needs a subscription whose
  policy allows the chosen data region **and** a Static Web Apps region (or an exemption for the
  SWA resource, which only serves static files). Re-run azure-validate (what-if) there.
  *Session 11:* a Pay-As-You-Go subscription without policies is now used for dev (uaenorth +
  SWA in eastasia, D140); the data region still needs the legal decision L3.
- **Q-T16** The Azure retail price list shows a Container Apps *Environment Management Hour* meter
  ($0.143/h, effective 2026-09-01). Confirm whether it applies to Consumption-only environments
  before relying on dev scale-to-zero savings (docs/azure-deployment.md cost table).
- **Q-T17** Resolved (Session 9, D133): confirmed the iframe could never render; PDFs are now
  downloads and nothing is framed.
- **Q-T18** Container Apps ingress must stay public for the SWA linked backend; whether the link
  restricts direct calls to the Container App FQDN is NOT VERIFIED (also Q-T13). A direct caller
  could pick its own anonymous throttle bucket (docs/security.md §7).
- **Q-T19** Production network isolation: without `ENABLE_PRIVATE_NETWORKING=true` PostgreSQL keeps
  the "Azure services" firewall rule (any tenant's Azure resources can reach the port; Entra-only
  sign-in still applies). Recommended on for prod; it adds VNet / private endpoint cost.

## Next session starts with

**dev phase 2 is live** (Session 12): https://victorious-meadow-0e5775b00.4.azurestaticapps.net,
backend image `medical-backend:35770c4…`, `/api/ready/` OK through the Static Web App. GitHub
`dev`/`dev-plan` variables are complete and `main` is protected (D143).
1. User: enable Arabic as the default language of the `signup-signin` user flow (portal,
   external tenant).
2. Admin sign-in: `amr_ashraf55@hotmail.com` is ADMIN now. Admins need `mfa` in `amr`
   (ENTRA_ADMIN_REQUIRE_MFA=true): set up MFA (Conditional Access in the external tenant) or the
   next admin sign-in is refused with MFA_REQUIRED. Add the user to the Entra admin group.
   Smoke-test a draft, a document upload (blob) and App Insights ingestion.
3. With user confirmation: push the local commits on a branch and open a PR (direct pushes to
   `main` are now refused). Merging it runs `backend.yml` / `infrastructure.yml` deploy-dev for
   the first time (the first CI deploy, which also exercises the OIDC identities).
4. After the first workflow run: design required status checks (path filters, see D143).
5. Local: fix host-run pytest (the compose PostgreSQL rejects the `medical` password from the
   host; probably a stale volume vs `.env`).
6. Carry-over: business questions / legal L1–L8, `/profile` page (deviation 32), Q-B19,
   deviation 66, `revoke_admin`.
