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

## Deviations from PROMPT.md

| # | PROMPT.md says | What we did | Why |
|---|---|---|---|
| 1 | §3/§5: `.claude/skills/medical-form-rules/SKILL.md` | `.claude/skills/syndicate-form-rules/SKILL.md` | explicit user instruction in Session 1 |
| 2 | §54 Phase 2: write plan with `writing-plans` (default path `docs/superpowers/plans/`) | `docs/plan.md` | explicit user instruction |
| 3 | §5 root folder `medical-insurance-platform/` | existing folder `Medical_App_Azure/` is the root | avoid a nested root; layout inside is identical |
| 4 | §54 phases 3–10 | re-cut into Sessions 2–10 (backend split in two, Azure integration + Docker image together, Bicep + CI together, docs last) | user-defined session boundaries; all phase content is covered |

## Open questions

Business questions 1–14 are tracked in `docs/business-rules.md` §10 (defaults implemented, to be
confirmed by the organization). Technical/environment questions for the user:

- **Q-T1** Azure subscription, region and Entra External ID tenant are not available in this session;
  Sessions 7–8 will generate everything and mark Azure-dependent checks `NOT VERIFIED — requires Azure credentials`.
- **Q-T2** Is Docker Desktop available on this Windows machine for Session 2 (PostgreSQL + Azurite via
  compose)? If not, a locally installed PostgreSQL 16 and `npx azurite` are the fallback.
- **Q-T3** Node 22 LTS and Python 3.12+ availability to be checked at the start of Session 2/4.
- **Q-T4** The `rtl` plugin's `rtl_check.py` path must be located via the `rtl-ui` skill in Session 4.

## Next session starts with

**Session 2 — Backend core** (`docs/plan.md` → Session 2).
1. Check toolchain: `python --version` (≥3.12), `docker compose version`, free port 5432/10000.
2. Task 2.1: Django project scaffold + settings split + requirements + `docker-compose.yml`
   (PostgreSQL 16 + Azurite) + pytest wired to PostgreSQL. Done when one trivial test passes against
   the compose database.
3. Then follow Tasks 2.2 → 2.10 in order with TDD; commit after each task.
4. Load `.claude/skills/syndicate-form-rules/SKILL.md`, `django-expert`, `django-safe-migration`
   and `postgresql-best-practices` before Task 2.2.
