# Final report — Medical Syndicates Treatment Project Platform

PROMPT.md §56, written at the end of Session 10 (Phase 10, deployment readiness) on 2026-10-06.
Repository: `C:\Users\admin\Desktop\Medical_App_Azure` (local Git, branch `main`, no remote —
nothing has been pushed). Every result below was produced in this session unless it says
otherwise.

**Overall status.** The application is complete and runs end to end locally (Docker Compose
PostgreSQL 16 + Azurite + Django, Vite SPA): doctor sign-in (dev auth), OCR with the mock
provider, form, beneficiaries, server fee quote, documents, receipt, submission with a reference
number, admin review, payment confirmation, approval, correction loop, A4 print. The Azure
infrastructure, Entra scripts and CI/CD exist and build/lint cleanly, but **no Azure resource and
no Entra tenant has been used: every Azure-side claim is NOT VERIFIED — requires Azure
credentials.**

---

## 1. Final architecture

```text
                        INTERNET
                           │ HTTPS
                           ▼
              ┌─────────────────────────────┐        ┌───────────────────────┐
              │ Azure Static Web App (Std)  │        │ Entra External ID     │
              │ React 19 + TS + Vite +      │        │ (sign-up / sign-in,   │
              │ Tailwind 4, Arabic RTL      │        │  MFA for admins)      │
              └──────────────┬──────────────┘        └──────────▲────────────┘
                             │ /api (linked backend, same origin)│ OIDC code flow + PKCE
                             ▼                                   │ (Django = confidential client)
              ┌─────────────────────────────┐───────────────────┘
              │ Azure Container Apps        │  HttpOnly SameSite=Lax session cookie, CSRF
              │ Django 5.2 + DRF + Gunicorn │──── jobs: migrate (once per deploy), cleanup (01:30 daily)
              └───┬────────┬────────┬───────┬───────────────┐
                  │        │        │       │               │  one user-assigned managed identity
                  ▼        ▼        ▼       ▼               ▼
          PostgreSQL   Blob      Key     Azure OpenAI   App Insights
          Flexible 16  Storage   Vault   (OCR, off by   + Log Analytics
          (Entra auth, (private, (RBAC,  default)
          TLS, PITR)   no keys)  purge protection)

GitHub Actions (OIDC; environments dev, staging, prod + *-plan)
   ├── frontend.yml ──────→ Static Web Apps
   ├── backend.yml ───────→ Container Registry → migrate job → new Container App revision
   ├── infrastructure.yml → Bicep what-if (PR) / deploy (main; prod needs a reviewer)
   └── e2e.yml ───────────→ docker compose + Playwright
```

Decisions that shape it:

- **Same origin (§4.1 option 1):** SWA Standard with the Container App as linked backend; the SPA
  calls relative `/api/v1/...`. Locally the Vite proxy does the same.
- **BFF authentication:** Django runs the OIDC code flow with PKCE, validates the ID token
  itself (signature, issuer, audience, nonce, expiry, tenant), maps users by `(oid, tid)`; the
  browser holds only a session cookie and never a token. No password forms.
- **Server-authoritative:** fees (`backend/apps/fees/services.py`), validation
  (`backend/apps/applications/validation.py`), document rules (`backend/apps/reference/document_rules.py`),
  status transitions (`backend/apps/applications/transitions.py` + `services.py`) and reference data
  are computed on the server and fetched by the SPA.
- **Stateless replicas:** sessions and rate-limit counters in PostgreSQL, files in Blob, secrets in
  Key Vault; migrations only in the job.

Diagrams (Mermaid): `docs/architecture.md`.

## 2. Repository tree

545 tracked files (`git ls-files | wc -l`), plus this session's additions.

```text
.
├── README.md  CLAUDE.md  PROMPT.md  .env.example  .gitignore  .gitattributes
├── docker-compose.yml  package.json  Makefile  skills-lock.json
├── .claude/skills/syndicate-form-rules/SKILL.md      project rules skill (fees, IDs, kinships, documents, statuses)
├── .github/workflows/
│   ├── frontend.yml  backend.yml  infrastructure.yml  e2e.yml
│   └── reusable-deploy-frontend.yml  reusable-deploy-backend.yml  reusable-infrastructure.yml
├── backend/
│   ├── Dockerfile  entrypoint.sh  manage.py  pyproject.toml  conftest.py  .dockerignore
│   ├── requirements/{base,dev,prod}.txt
│   ├── config/
│   │   ├── settings/{base,development,test,production}.py
│   │   ├── api/ (urls, error envelope, OpenAPI extensions)   db/entra_postgres/ (Entra token DB backend)
│   │   ├── azure.py secrets.py telemetry.py logging.py middleware.py health.py gunicorn.py envfile.py urls.py
│   │   └── tests/
│   ├── apps/
│   │   ├── accounts/       User (UUID, role, entra oid/tid), OIDC BFF, dev auth, grant_admin, seed_dev_data
│   │   ├── doctors/        member profile
│   │   ├── applications/   applications, transitions, reference numbers, validation, admin API
│   │   ├── beneficiaries/
│   │   ├── documents/      metadata, Blob storage, upload validators, cleanup_blobs
│   │   ├── fees/           FeeSchedule + fee engine, FY 2026 seed migration
│   │   ├── ocr/            providers (mock, azure_openai), Arabic prompts/schemas, normalizers
│   │   ├── reference/      constants, national_id.py, document_rules.py, reference-data API
│   │   ├── audit/          append-only AuditLog
│   │   └── common/         client address behind trusted proxies
│   │   (each with services.py, api/, migrations/, tests/)
│   ├── scripts/{smoke_api.py, local_postgres_tls.py}
│   └── tests/              cross-app e2e flow, helpers
├── frontend/
│   ├── index.html (lang="ar" dir="rtl")  package.json  vite.config.ts  playwright.config.ts  eslint.config.js
│   ├── public/staticwebapp.config.json   routes, CSP, security headers
│   ├── scripts/rtl_check.py
│   ├── e2e/  foundation, doctor-submit, admin-approve, correction-loop, print-a4, mobile-form specs + fixtures
│   └── src/
│       ├── api/ (typed client, case mapping, endpoints, generated schema.d.ts)   auth/ (RequireRole, session)
│       ├── components/form/ (NidInput, BoxStringInput, DashedField, RadioBoxGroup, ProgressStepper, …)  components/ui/
│       ├── features/ application-form · beneficiaries · documents · fees · applications · admin · reference
│       ├── pages/ public · doctor · application (Form, Payment, Review, Status, Print) · admin
│       ├── layouts/  i18n/ar.ts  utils/  index.css (theme tokens)  print.css  router.tsx
├── infrastructure/
│   ├── main.bicep  bicepconfig.json
│   ├── modules/ identity, monitoring, key-vault, storage, postgres, container-registry, container-apps-env,
│   │            container-app (+ migrate and cleanup jobs), static-web-app, static-web-app-link,
│   │            role-assignments, openai, network, private-endpoints
│   ├── parameters/{dev,staging,prod}.bicepparam
│   └── scripts/ create-entra-app.{sh,ps1}, setup-github-oidc.{sh,ps1}, setup-postgres-entra.sh,
│                check-template-security.py
└── docs/ architecture, database, api, business-rules, azure-deployment, entra-setup, github-setup,
          security, ocr, local-development, verification, plan, progress, final-report, screenshots/
```

## 3. Database schema

PostgreSQL 16, UUID primary keys, `ON DELETE PROTECT` on every foreign key, 26 migrations on a
clean database (11 project migrations). Full ER diagram, every constraint and index:
`docs/database.md`.

| Table | Purpose | Key constraints |
|---|---|---|
| `accounts_user` | identity (DOCTOR / ADMIN), Entra `oid` + `tid` | unique e-mail (also case-insensitive), unique `(entra_oid, entra_tid)`, role CHECK |
| `doctors_doctor` | member profile (1:1 user) | **unique `national_id`** (14-digit CHECK), unique `user_id`; `(syndicate_type, registration_number)` indexed, not unique |
| `applications_insuranceapplication` | per-fiscal-year application, status, payment status, reference number, `fee_snapshot`, `submitted_snapshot`, review fields | **partial unique `(doctor_id, fiscal_year) WHERE status <> 'REJECTED'`**; unique `reference_number`; CHECK: reference number present exactly when not DRAFT; enum CHECKs; indexes `(status, submitted_at)`, `(fiscal_year, status)`, `(payment_status)` |
| `applications_referencecounter` | sequence per fiscal year (row-locked) | unique `fiscal_year` |
| `applications_adminnote` | internal admin notes | index `(application_id, created_at)` |
| `beneficiaries_beneficiary` | family members (row 1..20, business max 10) | **partial unique `(application_id, national_id)`**, unique `(application_id, row_number)` |
| `documents_document` | file metadata (bytes in Blob) | **one live document per slot** `(application, beneficiary, type) NULLS NOT DISTINCT WHERE deleted_at IS NULL`; unique `blob_name`; type must match owner |
| `fees_feeschedule` | versioned fee schedule per fiscal year (FY 2026 seeded) | unique `(fiscal_year, version)`, one active per year; locked once used |
| `audit_auditlog` | append-only audit trail | trigger refuses UPDATE/DELETE |

## 4. Main API endpoints

Base `/api/v1/`, snake_case JSON, error envelope `{"error": {"code", "message", "fields"}}`.
Full table with notes and error codes: `docs/api.md`; OpenAPI at `/api/schema/` and Swagger UI at
`/api/docs/` (development).

| Area | Endpoints |
|---|---|
| Auth (BFF) | `GET auth/login/`, `GET auth/callback/`, `POST auth/logout/`, `GET auth/me/`; dev only: `GET auth/dev/users/`, `POST auth/dev/login/` |
| Reference | `GET reference-data/` (governorates, enums with Arabic labels, kinships, document rules, limits, `ocr_enabled`) |
| Profile | `GET/PATCH profile/` |
| Applications | `GET/POST applications/`, `GET/PATCH applications/{id}/`, `GET applications/{id}/fees/` (server quote), `GET applications/{id}/validation/`, `POST applications/{id}/submit/` |
| Beneficiaries | `GET/POST applications/{id}/beneficiaries/`, `PATCH/DELETE applications/{id}/beneficiaries/{bid}/` |
| Documents | `POST applications/{id}/documents/` (multipart), `GET/DELETE documents/{id}/`, `GET documents/{id}/content/` (authorized stream or ≤ 5-min SAS), `POST documents/{id}/extract/` (OCR suggestions) |
| Admin | `GET admin/stats/`, `GET admin/applications/` (search, filters, ordering, pagination ≤ 100), `GET admin/applications/{id}/`, `POST …/transition/`, `POST …/payment/`, `GET/POST …/notes/`, `GET …/audit/`, `GET admin/doctors/`, `GET admin/doctors/{id}/`, `GET/POST admin/fee-schedules/`, `GET admin/fee-schedules/{id}/` |
| Probes | `GET /api/health/` (liveness), `GET /api/ready/` (database) |

## 5. Azure services (defined in Bicep — none created yet)

**NOT VERIFIED — requires Azure credentials.** No resource was created; the only subscription
available during development is disabled (read-only) and its policy allows no Static Web Apps
region (Q-T15). Per environment (one resource group, `infrastructure/main.bicep`):

| Service | Module | Configuration |
|---|---|---|
| User-assigned managed identity | `identity.bicep` | used by the app and both jobs for every Azure call |
| Log Analytics + Application Insights | `monitoring.bicep` | retention / daily cap per environment; Entra-only ingestion in staging/prod |
| Key Vault | `key-vault.bicep` | RBAC, soft delete, purge protection; secrets set out of band |
| Storage account + private container `medical-documents` | `storage.bicep` | no public access, shared keys disabled, TLS 1.2, soft delete, versioning, lifecycle |
| PostgreSQL Flexible Server 16 | `postgres.bicep` | Entra auth (password auth off), TLS required, PITR, geo backup in prod |
| Container Registry | `container-registry.bicep` | no admin user, no anonymous pull |
| Container Apps environment | `container-apps-env.bicep` | Consumption workload profile, logs to Log Analytics |
| Container App + `migrate` job + `cleanup` job | `container-app.bicep` | Key Vault references, probes, HTTP-concurrency scaling, HTTPS-only ingress |
| Static Web App (Standard) + linked backend | `static-web-app.bicep`, `static-web-app-link.bicep` | `/api/*` → Container App; PR previews disabled |
| Role assignments | `role-assignments.bicep` | Blob Data Contributor (container), Blob Delegator, Key Vault Secrets User, AcrPull, Monitoring Metrics Publisher, OpenAI User — each on one resource |
| Azure OpenAI + vision deployment (optional) | `openai.bicep` | only with `enableOcr`; key auth disabled |
| VNet, private endpoints, private DNS (optional) | `network.bicep`, `private-endpoints.bicep` | only with `enablePrivateNetworking` |

Not created by Bicep: the Entra External ID tenant and app registrations
(`infrastructure/scripts/create-entra-app.{sh,ps1}`), the PostgreSQL database and app role
(`setup-postgres-entra.sh`), GitHub OIDC identities (`setup-github-oidc.{sh,ps1}`).

## 6. Required environment variables

Every variable, its default and meaning: `README.md` §4 (names only in `.env.example`). Locally
none is required. In Azure all are set by `main.bicep`; the operator provides only these
shell/GitHub environment values before deploying:

| Value | Where it comes from |
|---|---|
| `KEY_VAULT_OPERATOR_OBJECT_ID`, `KEY_VAULT_OPERATOR_TYPE` | `az ad signed-in-user show --query id -o tsv` (first phase, human only) |
| `ENTRA_AUTHORITY`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | printed by `create-entra-app` |
| `CONTAINER_IMAGE` | `<acr>.azurecr.io/medical-backend:<git sha>` (empty = first phase) |
| optional: `STATIC_WEB_APP_LOCATION`, `PUBLIC_HOSTNAME`, `ENABLE_OCR`, `ENABLE_PRIVATE_NETWORKING`, `POSTGRES_ENTRA_ADMIN_OBJECT_ID/_NAME/_TYPE` | operator decisions |
| GitHub only: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `ACR_NAME`, `CONTAINER_APP_NAME`, `MIGRATE_JOB_NAME`, `CLEANUP_JOB_NAME`, `STATIC_WEB_APP_NAME` | `setup-github-oidc` output and Bicep outputs (`docs/github-setup.md` §4) |

Secrets (Key Vault only, never in Git or GitHub): `django-secret-key` (operator, README §11
step 4), `entra-client-secret` (written by `create-entra-app`), `database-password` (only with
`DB_AUTH_MODE=password`, not used by the template). The Application Insights connection string is
passed by Bicep as a Container Apps secret (not a Key Vault secret; with Entra-only ingestion it
grants nothing on its own).

Production settings refuse to start when `DEBUG` or `DEV_AUTH_ENABLED` is on, the secret key is
missing or shorter than 50 characters, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`DATABASE_URL`/Entra
settings are missing, TLS is off, Blob account keys or the in-memory backend are configured, or
OCR is on with the mock provider or incomplete Azure OpenAI settings.

## 7. Local development instructions

```bash
docker compose up -d --build                 # PostgreSQL 16 + Azurite + Django :8000 (migrates + seeds)
curl http://localhost:8000/api/ready/        # PowerShell: curl.exe …
cd frontend && npm ci && npm run dev         # http://localhost:5173 → sign in as admin@dev.local / doctor@dev.local
npm run test:backend                         # from the repo root
cd frontend && npm run ci && npx playwright test
```

Seeded users, shortcuts, ports, host-run Django, the production image locally and PowerShell
variants: `README.md` §3–§8 and `docs/local-development.md`.

## 8. Entra External ID setup steps

**NOT VERIFIED — requires Azure credentials** (scripts syntax-checked only). Details:
`docs/entra-setup.md`.

1. Create an **external** tenant (Entra admin center → External ID → Create a tenant → External);
   note the tenant id; authority = `https://<name>.ciamlogin.com/<tenant-id>`.
2. User flow `signup-signin`: e-mail + password (or e-mail OTP), collect *Display Name* only,
   enable Arabic as default language, company branding with the privacy-policy link.
3. After the first infrastructure phase (Key Vault exists), per environment:
   `infrastructure/scripts/create-entra-app.sh --environment <env> --tenant-id <tenant-id>
   --public-url https://<swa-host> --key-vault <kv> --subscription <sub> --user-flow-id <flow-id>`
   (PowerShell: `create-entra-app.ps1 -Environment … -TenantId … -PublicUrl … -KeyVault …
   -Subscription … -UserFlowId …`). It registers a Web (confidential) app with redirect URIs
   `/api/v1/auth/callback/` and `/signed-out`, implicit grant off, `openid profile email`, the
   `email` optional claim, and writes a 1-year client secret to Key Vault without printing it.
4. Group `medical-admins-<env>` + Conditional Access policy *Require MFA* on the app; Django also
   refuses an admin session without `mfa` in `amr` (`ENTRA_ADMIN_REQUIRE_MFA=true`).
5. Rotate the secret yearly: same script with `--rotate-secret`, restart the revision, delete the
   old credential.

## 9. Azure deployment instructions

**NOT VERIFIED — requires Azure credentials.** Exact Bash and PowerShell commands: `README.md`
§9–§14; reasons and details: `docs/azure-deployment.md`; CI/CD setup: `docs/github-setup.md`.

1. Register providers; `az group create -n rg-medsyn-<env> -l <region>`.
2. `export KEY_VAULT_OPERATOR_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)`; leave
   `CONTAINER_IMAGE` unset.
3. First phase: `az deployment group what-if` then `create` with
   `-f infrastructure/main.bicep -p infrastructure/parameters/<env>.bicepparam`.
4. `az keyvault secret set --name django-secret-key --file <0600 temp file>`.
5. `create-entra-app` (step 8.3); export `ENTRA_AUTHORITY`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`.
6. `infrastructure/scripts/setup-postgres-entra.sh --resource-group … --server … --identity-name …
   --database medical --allow-current-ip`.
7. Build and push `backend/` (`docker build --target runtime`), set `CONTAINER_IMAGE`, deploy
   again (second phase), start the `migrate` job and wait for `Succeeded`, `curl …/api/ready/`.
8. `npm run build` in `frontend/`, deploy `frontend/dist` with the SWA CLI (token read at run time).
9. Sign in once, then `az containerapp exec … --command "python manage.py grant_admin <email>"`.
10. GitHub: create the repository (only after your confirmation), environments `dev|staging|prod`
    (+ `-plan`), `setup-github-oidc` per environment, variables, branch protection. From then on
    every push to `main` deploys.

Things to know for the **next deployment**: every user is signed out once (D131: the session hash
now includes the role); `TRUSTED_PROXY_COUNT=2` is new and assumes the SWA linked backend and the
Container Apps ingress each append one `X-Forwarded-For` entry (Q-T13, NOT VERIFIED).

## 10. Approximate Azure cost drivers

List prices (USD, `westeurope`, Azure Retail Prices API, 2026-10-06); details and controls in
`docs/azure-deployment.md` *Cost*.

| Driver | dev (cheapest reasonable) | prod (initial) |
|---|---|---|
| PostgreSQL compute | Burstable B1ms ≈ $14.5/month | General Purpose D2ds_v5 ≈ $155/month (HA would double it) |
| PostgreSQL storage + backups | 32 GB, 7-day PITR | 64 GB, 35-day PITR, geo-redundant |
| Container Apps vCPU-seconds / min replicas | 0.5 vCPU, min 0 (scale to zero) | 1 vCPU / 2 GiB, min 1 (≈ $31 idle – $110 busy per replica-month), max 5 |
| Static Web Apps Standard | $9/month (needed for the linked backend) | $9/month |
| Blob storage + transactions | LRS, small | ZRS; versions + soft delete add stored GB |
| Log Analytics ingestion | 1 GB/day cap | $2.99/GB, no cap, 90 days — largest variable cost |
| Azure OpenAI tokens per OCR call | off | off until legal approval; image tokens per call |
| Private networking | off | private endpoints + DNS per hour/GB if enabled |
| Container Registry | Basic ≈ $5/month | Standard ≈ $20/month |
| Container Apps environment | possible management-hour meter ($0.143/h) — Q-T16 | same |

Rough production total before private networking and OCR: **$250–350 per month** (estimate, not
a quote). Grow `maxReplicas` first, then CPU/memory, then the PostgreSQL SKU and HA.

## 11. Security decisions

Details, the Session 9 review (F1–F8) and the legal decisions: `docs/security.md`.

- Entra External ID with the BFF pattern; PKCE, state, nonce; ID token validated independently;
  users mapped by `(oid, tid)`, never by e-mail; no password forms; no tokens in the browser.
- Session cookie `HttpOnly; Secure; SameSite=Lax`, idle 2 h / absolute 12 h, bound to the role
  (role change ends sessions); CSRF on every unsafe method.
- Admin role only via `manage.py grant_admin` (audited); admin MFA enforced (`amr`) + Conditional
  Access.
- Object-level authorization on every endpoint (other doctor's object → 404); protected fields
  read-only for doctors; one transition service with `select_for_update` and audit.
- National ID: business identifier with unique constraints, never a key; masked
  (`29•••••••••123`) in admin lists, logs and telemetry; full reveal audited.
- Documents: private container, server-generated names, content sniffing + full image decode,
  8 MB cap enforced before the body is read, decompression-bomb limit, authorized stream or
  ≤ 5-minute user-delegation SAS; nothing is ever framed.
- OCR only on the server, authenticated, rate-limited, behind `OCR_ENABLED` (off in production
  until legal approval), suggestions only, payload never logged.
- Production hardening: startup refusal of unsafe configuration, HSTS, CSP, nosniff,
  `X-Frame-Options: DENY`, no CORS, no source maps, non-root container, Gunicorn access log off.
- Secrets only in Key Vault via managed identity; no Blob account keys, no OpenAI keys, no ACR
  admin user, no stored Azure credentials in GitHub (OIDC, `main`-only deploy environments,
  reviewers for prod, a deployer that cannot grant itself data access).
- Rate limits: sign-in callback 20/min per client address (trusted-proxy aware), uploads 60/h and
  OCR 30/h per user, shared cache.
- No compliance claim (Law 151/2020, GDPR, HIPAA). Decisions L1–L8 (religion field, OCR by an AI
  service, region, retention, admin access, breach procedure, production access, malware
  scanning) are open — `docs/security.md` §0 and §6.

## 12. Prototype features ported and §2.3 defects fixed

### 12.1 Features ported (behaviour, not code; no Firebase code or configuration copied)

| Prototype | New implementation |
|---|---|
| `context/FormContext.jsx` (state, autosave) | `frontend/src/features/application-form/ApplicationFormProvider.tsx`, `useApplicationDraft.ts`, `draftController.ts` (debounced autosave to the API, upload-on-select) |
| `pages/FormPage.jsx` (paper form, validation panel, action bar, print) | `frontend/src/pages/application/FormPage.tsx`, `PaperForm.tsx`, `components/form/ValidationErrorPanel.tsx`, `StickyActionBar.tsx`, `src/print.css` |
| `MemberSection.jsx`, `BeneficiaryTable.jsx`, `DeclarationSection.jsx` | `features/application-form/MemberSection.tsx`, `features/beneficiaries/BeneficiaryTable.tsx` (+ mobile cards), `features/application-form/DeclarationSection.tsx` |
| `FeeSummaryPanel.jsx` | `features/fees/FeeSummaryPanel.tsx` showing the server quote |
| `components/shared/*` | `components/form/NidInput.tsx`, `BoxStringInput.tsx`, `DashedField.tsx`, `RadioBoxGroup.tsx`, `ProgressStepper.tsx`; `features/beneficiaries/DocumentModal.tsx` |
| `SmartUpload.jsx` | `features/documents/SmartUpload.tsx` (upload to the API, "مسح تلقائي" calls the server) |
| `CalculationService.js` | `backend/apps/fees/services.py` (FY 2026 schedule, tiers, admin fee, 70+ cap) |
| `OcrService.js` (prompts, mapping, normalization) | `backend/apps/ocr/` (`schemas.py` Arabic prompts, `normalizers.py`, `providers/mock.py`, `providers/azure_openai.py`) |
| `validateForm.js` | `backend/apps/applications/validation.py` (authoritative, all §22 messages); the SPA shows its result in the error panel and inline (`GET /applications/{id}/validation/` after each autosave) plus local hints (`features/application-form/nationalId.ts`, `features/documents/preCheck.ts`) |
| `validateReceiptImage.js` | `backend/apps/documents/validators.py` + `features/documents/preCheck.ts` |
| `ReceiptPage.jsx`, `WaitingPage.jsx`, `DashboardPage.jsx` | `pages/application/PaymentPage.tsx`, `StatusPage.tsx` (polling timeline), `pages/doctor/DashboardPage.tsx` |
| `functions/index.js` (reference number) | `backend/apps/applications/services.py` (atomic, at first submission) |
| `auth/AuthPage.jsx` | Entra External ID hosted pages + `pages/public/LandingPage.tsx` |
| `index.css` tokens | Tailwind 4 `@theme` in `frontend/src/index.css` |
| (new) admin area | `pages/admin/*`: dashboard tiles, applications list (server-side filters/search/sort/pagination), detail with document viewer, payment, transitions, notes, audit, print; doctors; fee schedules |

### 12.2 PROMPT.md §2.3 checklist

| # | Defect not reproduced | Fixed by | Tests that prove it |
|---|---|---|---|
| 1 ✓ | Owner-editable payment status | payment and application status read-only on every doctor serializer; only admin services change them | `apps/applications/tests/test_submit.py::test_doctor_cannot_set_payment_status`; `apps/applications/tests/test_api.py::test_patch_protected_fields_ignored`, `::test_patch_protected_payment_status_on_submitted_app_is_refused_and_unchanged` |
| 2 ✓ | Resubmit by client status write | explicit `NEEDS_CORRECTION → SUBMITTED` through `POST /applications/{id}/submit/` and the transition service | `apps/applications/tests/test_api.py::test_resubmit_after_needs_correction_keeps_reference_number`; `apps/applications/tests/test_transitions.py`; e2e `frontend/e2e/correction-loop.spec.ts` |
| 3 ✓ | Public download URLs | private container; authorized stream or ≤ 5-min read-only SAS; no shared keys | `apps/documents/tests/test_api.py::test_content_requires_owner_or_admin`, `::test_upload_returns_summary_without_storage_details`, `::test_pdf_content_is_a_download_never_framed`; `apps/documents/tests/test_storage.py::test_content_sas_ttl_at_most_300s_and_read_only`; `infrastructure/scripts/check-template-security.py` |
| 4 ✓ | Browser-side fee snapshot | fee engine and snapshot only on the server at submission | `apps/fees/tests/test_engine.py::test_worked_examples`; `apps/applications/tests/test_submit.py::test_submit_writes_snapshot_and_audit`; `apps/applications/tests/test_api.py::test_fees_of_a_submitted_application_are_the_frozen_snapshot` |
| 5 ✓ | Browser-only validation | `validation.py` runs on every submission and returns all errors | `apps/applications/tests/test_submit.py::test_submit_with_errors_raises_validation_failed_and_changes_nothing`; `apps/applications/tests/test_api.py::test_submit_errors_return_every_message_grouped_by_step` |
| 6 ✓ | No national-ID uniqueness | unique constraints (doctor, beneficiary per application) + one active application per year; `IntegrityError` handled | `apps/doctors/tests/test_models.py`; `apps/doctors/tests/test_api.py::test_concurrent_duplicate_national_id_one_wins`; `apps/beneficiaries/tests/test_constraints.py::test_beneficiary_duplicate_national_id_in_application_fails`; `apps/applications/tests/test_constraints.py::test_second_active_application_same_year_violates_constraint` |
| 7 ✓ | Upload-at-end, orphaned files, lost form | draft autosave, upload-on-select, nightly orphan cleanup | `frontend/src/features/application-form/useApplicationDraft.test.tsx`, `features/documents/SmartUpload.test.tsx`; `apps/documents/tests/test_cleanup.py::test_orphan_blob_without_metadata_removed_after_grace`, `::test_cleanup_removes_soft_deleted_after_grace` |
| 8 ✓ | Dropped Arabic digits | ٠-٩ normalized to Western digits in the SPA and the API | `frontend/src/components/form/NidInput.test.tsx`; `apps/reference/tests/test_national_id.py::test_normalizes_arabic_digits_and_strips_separators`; `apps/doctors/tests/test_api.py::test_profile_accepts_arabic_digits`; e2e `mobile-form.spec.ts` |
| 9 ✓ | Browser-side OCR with exposed key | server-side OCR, authenticated, rate-limited, managed identity (no key) | `apps/ocr/tests/test_api.py::test_anonymous_401`, `::test_rate_limit_31st_call_429`, `::test_rate_limit_is_per_user`, `::test_extract_only_suggests_and_saves_nothing`; `frontend/src/staticWebAppConfig.test.ts` (CSP `connect-src 'self'`) |
| 10 ✓ | Committed Firebase config, EOL Node | no secrets in Git; Python 3.12, Node 22 | gitleaks (this session: 14 commits, no leaks); `backend/Dockerfile` `python:3.12-slim`; workflows `node-version: "22"`; `frontend/package.json` `engines.node >=22` |
| 11 ✓ | Inconsistent child document rules | one rules table drives validator, DocumentModal and checklist | `apps/reference/tests/test_api.py::test_document_rules_come_from_the_single_rules_table`; `frontend/src/features/beneficiaries/BeneficiaryTable.test.tsx`, `DocumentModal.test.tsx` |
| 12 ✓ | Reference number on create | generated atomically at first submission; DB CHECK forbids it on drafts | `apps/applications/tests/test_constraints.py::test_draft_cannot_carry_a_reference_number`; `apps/applications/tests/test_reference_numbers.py::test_concurrent_submits_of_the_same_application_produce_one_number`; `apps/applications/tests/test_api_concurrency.py::test_parallel_submissions_get_unique_sequential_reference_numbers` |

All backend test paths are relative to `backend/`. Every cited test function was checked to exist
in this session.

## 13. Remaining limitations

**Azure / external (NOT VERIFIED — requires Azure credentials):**

- Nothing was deployed: `az deployment group what-if`, the Container App, jobs, SWA linked
  backend, managed-identity access to PostgreSQL / Blob / Key Vault / OpenAI, Application Insights
  export and the GitHub OIDC flow have never run. The available subscription is read-only and
  its policy offers no Static Web Apps region (Q-T1, Q-T15).
- Entra External ID: no tenant; the `email` and `amr` claims and the Arabic hosted pages are
  unverified (Q-T7).
- Behind the linked backend: the `Host` header, `X-Forwarded-Proto`, the number of
  `X-Forwarded-For` entries (`TRUSTED_PROXY_COUNT=2`) and request-body limits (Q-T13); whether the
  Container App FQDN can be called directly, bypassing the SWA (Q-T18).
- PostgreSQL without `ENABLE_PRIVATE_NETWORKING` keeps the "Azure services" firewall rule (Q-T19).
- Container Apps environment management meter (Q-T16); Application Insights Entra vs.
  connection-string ingestion for dev (Q-T14).
- No restore drill has been run; Azure Policy deny rules for the deployer identity are not
  written; Defender for Storage malware scanning and alerting are not configured.
- The first-ever deployment serves errors until the first migrate job finishes (later
  deployments migrate first).

**Application:**

- `/profile` is still a placeholder page; the member data is edited on the form (deviation 32).
- Payment instructions on the receipt page are placeholder text in `frontend/src/i18n/ar.ts`
  (business question 8 / Q-B19).
- `grant_admin` has no counterpart: revoking the admin role needs a Django shell
  (`User.role = "DOCTOR"`, which ends the user's sessions) and is not audited.
- An admin cannot change a payment decision after APPROVED (Q-B15).
- PDFs are not sent to OCR (clear `OCR_UNAVAILABLE` message); PDF and HEIC uploads are off by
  default.
- **React Hook Form and Zod are installed but not used** (PROMPT.md §6/§41 name them): the form
  state lives in `ApplicationFormProvider` + `draftController.ts`, and instant feedback comes from
  the server's `/validation/` endpoint after each autosave plus local hints (national-ID parsing,
  receipt pre-check, box inputs). Behaviour matches §41 (server authoritative, immediate
  feedback); either adopt them for field-level checks or remove `react-hook-form`, `zod` and
  `@hookform/resolvers` from `frontend/package.json`.
- Locally, Playwright runs leave `e2e-*@dev.local` data in the dev database (Q-T12).
- Tooling: Node 22.11 on this machine (jsdom 26 instead of 27, Q-T9); the vendored
  `frontend/scripts/rtl_check.py` has no license file upstream (Q-T8); Cairo is loaded from Google
  Fonts (Q-T10).
- Skills/plugins (PROMPT.md §3): the `security-review` skill could not run (it needs a git
  remote; a manual review with the same scope was done in Session 9); the GitHub plugin was not
  used because nothing may be pushed or created without your confirmation (and its MCP server
  failed to connect in this session); `azure-deploy` was not used (no billable resources without
  confirmation).

## 14. Open business questions (PROMPT.md §57)

Each has a default implemented in one configurable place (`docs/business-rules.md` §10). Items 1–12
are §57; 13–21 came up during implementation.

| # | Question | Default implemented | Where |
|---|---|---|---|
| 1 | Are the FY 2026 amounts, tiers, admin fees and the 70+ cap final? | §17.1 values in an editable, versioned `FeeSchedule` | admin fee-schedules page |
| 2 | Fees for a deceased (متوفى) member's family? | same as WORKING | `apps/fees/services.py` |
| 3 | Fees for an `ADDITION` application — only new beneficiaries? | same as FIRST_TIME | `apps/fees/services.py` |
| 4 | Children's documents: age-16 rule (birth certificate < 16, national ID ≥ 16, birth certificate always if the member is female)? | age-aware rule | `CHILD_NATIONAL_ID_AGE=16` |
| 5 | Maximum beneficiaries: 10 or 11? | 10 | `MAX_BENEFICIARIES` |
| 6 | `SON_MINOR` ≤ 18 and spouse kinship matching the member's gender? | both enforced | `ENFORCE_SON_MINOR_AGE`, `SON_MINOR_MAX_AGE`, `ENFORCE_SPOUSE_GENDER` |
| 7 | Can a rejected applicant re-apply in the same fiscal year? | yes, a new application | partial unique constraint |
| 8 | How do members pay; what instructions? | placeholder text | `frontend/src/i18n/ar.ts` `payment.instructions` |
| 9 | Is the member photo mandatory? | optional | `REQUIRE_MEMBER_PHOTO=false` |
| 10 | Is `(syndicate_type, registration_number)` unique? | indexed, not unique | `apps/doctors/models.py` |
| 11 | Is sending ID images to Azure OpenAI approved, and in which region? | OCR behind a flag, off in production | `OCR_ENABLED`, Bicep `enableOcr` |
| 12 | Retention period for applications and documents? | nothing auto-deleted; documented as a decision | `docs/security.md` L4 |
| 13 | Validate the national ID check digit (position 14)? | not validated | `apps/reference/national_id.py` |
| 14 | Unknown governorate-of-birth code: block or warn? | warning | `apps/reference/national_id.py` |
| 15 | Arabic payment-status labels; payment change after APPROVED? | labels `لم يتم رفع الإيصال / بانتظار التأكيد / مؤكد / مرفوض`; refused after APPROVED | `apps/reference/constants.py`, `set_payment_status` |
| 16 | Should admins see drafts? | no | admin querysets |
| 17 | Receipt minimum 400×300 in landscape only, or either orientation? | landscape (prototype rule) | `RECEIPT_MIN_WIDTH/HEIGHT` |
| 18 | Should `إنشاء حساب` open Entra sign-up directly? | combined sign-up/sign-in flow | `LandingPage.tsx` |
| 19 | Must official printouts carry the full national ID? | masked unless revealed (audited) | `AdminPrintPage.tsx` |
| 20 | Does a CONFIRMED payment stay confirmed after a correction/resubmission? | yes, unless the receipt is replaced | `apps/applications/services.py` |
| 21 | Legal decisions L1–L8 (religion field, OCR, region, retention, admin access, breach procedure, production access, malware scanning) | see `docs/security.md` §6 | — |

## 15. Tests executed and their results

Run on 2026-10-06 (Windows 10, Docker Desktop 29.7.2, Node 22.11, Python 3.12 in the
containers) after the last code change of this session. Earlier evidence (actionlint, dependency
audits, live header checks, clean-database migration run): `docs/verification.md`.

| Check | Command | Result |
|---|---|---|
| Backend lint | `docker compose exec backend sh -c 'ruff check . && ruff format --check .'` | All checks passed; 235 files formatted |
| Django checks | `python manage.py check`; `makemigrations --check --dry-run` | no issues; No changes detected |
| Backend tests (PostgreSQL 16 + Azurite) | `npm run test:backend` | **964 passed, 1 skipped** in 46.5 s (the skipped test needs the repository root, not mounted in the container) |
| New regression tests on the host | `cd backend && .venv/Scripts/python -m pytest -q config/tests/test_envfile.py` | 5 passed |
| Frontend CI | `cd frontend && npm run ci` | ESLint clean; `tsc` (app + node) clean; Vitest **281 passed in 41 files**; `rtl_check.py`: 0 errors, 0 warnings in 126 files; `vite build` OK |
| End-to-end | `cd frontend && npx playwright test` | **11 passed, 5 skipped** (each spec runs in its own desktop/mobile project): doctor submit with OCR and 3٬025 ج.م, admin approve, correction loop (same reference number), A4 print (doctor and admin PDFs: 2 pages each), 390×844 phone form, foundation |
| Production image | `docker build --target runtime -t medical-backend:runtime backend/` | built, 432 MB |
| Deploy check | `docker run --rm --entrypoint python --env-file bicep.env … medical-backend:runtime manage.py check --deploy` (the environment `main.bicep` sets, placeholder Azure ids) | System check identified no issues; with `DEV_AUTH_ENABLED=true`: `ImproperlyConfigured` (refused) |
| Bicep | `az bicep build --file infrastructure/main.bicep`; `az bicep build-params` × 3 | OK (Bicep 0.48.1) |
| Template guard | `python infrastructure/scripts/check-template-security.py main.json [--self-test]` | 0 problems; self-test 20/20 |
| Fresh stack (PowerShell variant) | `$env:POSTGRES_PORT=…; docker compose -p medical-fresh up -d` … `down -v` | ready `{"database": "ok"}`, 0 unapplied migrations, `grant_admin` granted / refused an unknown user (exit 1) |
| README commands | every `bash` block `bash -n`, every `powershell` block through the PowerShell parser (placeholders substituted); `az … --help` for each restore command and flag | 10/10 Bash, 7/7 PowerShell parse; all `az` flags exist |
| Diagrams | every Mermaid block in `docs/architecture.md` and `docs/database.md` through the Mermaid 11 parser | 9/9 parse (two sequence diagrams in `architecture.md` had a `;` that broke rendering — fixed) |
| Secrets | `gitleaks git` (history) and `gitleaks dir` (this session's changed files) | no leaks found (14 commits) |
| Azure what-if, deployment, Entra sign-in, managed identity, restore | — | **NOT VERIFIED — requires Azure credentials** |

**Bug found and fixed in this session (documentation review):** `.env.example` says "copy to
`.env`", but development settings loaded every line of the root `.env`, so a verbatim copy turned
every setting into an empty string — host-run Django crashed (`ValueError: invalid literal for
int()`), and `DEV_AUTH_ENABLED`/`OCR_ENABLED` would have silently become false. Reproduced first,
then fixed test-first: `backend/config/envfile.py::read_env_file` skips empty values and never
overrides the real environment (`backend/config/tests/test_envfile.py`, 5 tests); a copied
`.env.example` now loads with every default intact.
