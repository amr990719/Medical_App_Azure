# CLAUDE.md — Medical Syndicates Treatment Project Platform

Digital replica of the paper subscription form of the Egyptian Union of Medical Professions
Syndicates treatment project (اتحاد نقابات المهن الطبية — مشروع علاج الأعضاء وأسرهم).
Doctors fill the form in Arabic (RTL), upload ID documents, add family beneficiaries, pay, and
submit. Administrators review, confirm payment, and approve.

**The specification is `PROMPT.md`.** Where this file and PROMPT.md disagree, PROMPT.md wins.
Where two PROMPT.md sections disagree, the more specific one wins.

## Session workflow

1. Read `docs/progress.md` first ("Next session starts with"), then the matching session in `docs/plan.md`.
2. Load `.claude/skills/syndicate-form-rules/SKILL.md` before touching fees, national IDs, kinships,
   documents or status transitions.
3. Work with TDD (superpowers `test-driven-development`), verify before claiming done
   (`verification-before-completion`), commit locally at the end of each session. **Never push,
   create repositories, open PRs, or create Azure resources without explicit confirmation.**
4. Update `docs/progress.md` (Done / Decisions / Deviations / Open questions / Next session) at the end.
5. The Firebase prototype is cloned read-only at `../reference/medical-form` (outside this repo).
   Port its behaviour, never its code or Firebase config.

## Repository layout

```text
backend/        Django 5 LTS + DRF, Python 3.12+, PostgreSQL (psycopg 3), Gunicorn
  config/settings/{base,development,test,production}.py
  apps/{accounts,doctors,applications,beneficiaries,documents,fees,ocr,reference,audit}
frontend/       React + TypeScript (strict) + Vite + Tailwind, Arabic RTL, TanStack Query, RHF + Zod
infrastructure/ Bicep modules, parameters, Entra scripts
.github/        GitHub Actions (frontend.yml, backend.yml, infrastructure.yml)
docs/           architecture, business rules, plan, progress, security, …
```

Business logic lives in `services.py` modules (and `validation.py`, `national_id.py`,
`document_rules.py`), never in views or serializers. Views only authenticate, authorize,
deserialize, call a service, serialize.

## Non-negotiable rules

### Server is authoritative
- Fees are calculated **only** in `backend/apps/fees/services.py`. The frontend displays the server quote
  (`GET /api/v1/applications/{id}/fees/`) and never computes money.
- Validation is authoritative in `backend/apps/applications/validation.py`. Frontend Zod schemas are UX only.
- Status, `payment_status`, `reference_number`, `fee_snapshot`, `review_notes` and reviewer fields are
  **read-only for doctors** on every serializer. Transitions go through one service
  (`applications/services.py::transition`) with `select_for_update`, an explicit transition table and audit entries.
- Reference numbers (`MED-{fy}-{000123}`) are generated atomically at **first submission**, never on create.
- Reference data (governorates, kinships, document rules, statuses, `MAX_BENEFICIARIES`) comes from
  `GET /api/v1/reference-data/`; the frontend never duplicates these tables.
- ONE document-rules table (`backend/apps/reference/document_rules.py`) drives the validator, the
  DocumentModal and the documents checklist.

### Privacy and security
- **Never log a full national ID.** Mask as first 2 + last 3 (`29•••••••••123`). A logging filter masks
  any 14-digit run. Never log tokens, cookies, passwords, document bytes, OCR prompts/payloads.
- National ID is a business identifier with a UNIQUE constraint, **never a primary key**. All PKs are UUIDs.
- Documents live in a **private** Blob container; metadata only in PostgreSQL. Access via the authorized
  `/documents/{id}/content/` endpoint or ≤5-minute SAS URLs. No permanent URLs, no files in the
  container filesystem, no binaries in PostgreSQL.
- OCR runs **server-side only**, authenticated, rate-limited, behind `OCR_ENABLED`; the browser never
  calls AI services. OCR suggests; it never saves.
- Object-level permissions on every endpoint; querysets scoped to the requesting doctor. Admin role is
  granted only via `manage.py grant_admin`.
- Authentication is Entra External ID via the BFF pattern (Django confidential client, PKCE, HttpOnly
  `SameSite=Lax` session cookie, CSRF on unsafe methods). **No password forms in the SPA.**
  `DEV_AUTH_ENABLED` works only in development/test settings; production refuses to start with it on.
- **No secrets in code or Git.** `.env.example` contains names only. Never invent Azure IDs or credentials.
- Rely on database constraints (unique national ID, one active application per doctor per fiscal year,
  unique beneficiary national ID per application) and handle `IntegrityError`; pre-checks are not enough.

### Infrastructure
- PostgreSQL is **never** inside a Docker container in production, and tests also run on PostgreSQL (no SQLite).
- Frontend (Static Web Apps) and Django (Container Apps) are separate deployables; same-origin `/api`
  through the SWA linked backend. Local dev uses the Vite proxy.
- Migrations run once per deployment as a Container Apps job, never on replica start; expand/contract only.
- Use current runtimes: Python 3.12+, Node 22 LTS.

### Arabic / RTL / i18n (frontend)
- `<html lang="ar" dir="rtl">` in `index.html`. Font: Cairo with fallback stack.
- **Every UI string lives in `frontend/src/i18n/ar.ts`.** No hard-coded strings in components.
- Use logical utilities only: `ms-* me-* ps-* pe-* start-* end-* text-start`. **Never** `ml-* mr-* left-* right-*`
  for layout. `rtl_check.py frontend/src` must pass.
- LTR inputs (`dir="ltr"`): national ID, phone, email, years, numbers.
- Accept Eastern Arabic digits (٠-٩) everywhere; normalize to Western digits before validation and
  storage, frontend **and** backend. Never silently drop them.
- Display with `ar-EG` locale (`3٬025 ج.م`, `٣ أكتوبر ٢٠٢٦`); store Western digits and ISO dates.
- Mirror directional icons (arrows, chevrons) in RTL; never mirror logos, checkmarks, media icons.
- Use the theme tokens in PROMPT.md §7.2 (banana, teal, charcoal, …) and status colours in §7.3.

### Prototype defects that must NOT be reproduced (PROMPT.md §2.3)
owner-editable payment status · resubmit by client status write · public download URLs · browser-side fee
snapshot · browser-only validation · no national-ID uniqueness · upload-at-end with orphaned files ·
dropped Arabic digits · browser-side OCR with exposed key · committed Firebase config / EOL Node ·
inconsistent child document rules · reference number on create.

## Conventions
- Python: ruff (line length 100), type hints, `Decimal`/int for money (never float), pytest + factory_boy,
  tests next to each app in `apps/<app>/tests/`.
- API: `/api/v1/`, snake_case JSON, error envelope `{"error": {"code", "message", "fields"}}` (PROMPT.md §46),
  drf-spectacular OpenAPI schema.
- TypeScript: strict, no `any`, camelCase in the SPA with a mapping layer to snake_case API types.
- Commits: conventional prefix (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), one logical change each.
- Report honestly: anything not verified against real Azure/Entra is marked
  `NOT VERIFIED — requires Azure credentials`.
