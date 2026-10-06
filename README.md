# Medical Syndicates Treatment Project Platform

Digital replica of the paper subscription form of the Egyptian Union of Medical Professions
Syndicates treatment project (اتحاد نقابات المهن الطبية — مشروع علاج الأعضاء وأسرهم —
استمارة اشتراك بمشروع العلاج). Doctors sign in with Microsoft Entra External ID, fill the form in
Arabic (right-to-left), upload their ID documents (optional server-side OCR pre-fills the form),
add up to 10 family beneficiaries, see the fee calculated by the server, upload the payment
receipt and submit. Administrators review, confirm payments, request corrections, approve or
reject, and print. Everything runs on Microsoft Azure.

- Specification: [`PROMPT.md`](PROMPT.md). Conventions and non-negotiable rules: [`CLAUDE.md`](CLAUDE.md).
- Final report (architecture, schema, endpoints, security, tests, open questions): [`docs/final-report.md`](docs/final-report.md).

> **Azure status.** All code, Bicep, scripts and workflows exist and were verified locally (tests,
> builds, `az bicep build`, `manage.py check --deploy` with the production environment). Nothing
> was deployed to Azure and no Entra tenant was used: every Azure step below is
> **NOT VERIFIED — requires Azure credentials**.

## Contents

1. [Architecture](#1-architecture)
2. [Repository layout](#2-repository-layout)
3. [Local setup](#3-local-setup)
4. [Environment variables](#4-environment-variables)
5. [Database migrations](#5-database-migrations)
6. [Seeding](#6-seeding)
7. [Running tests](#7-running-tests)
8. [Docker](#8-docker)
9. [Azure prerequisites](#9-azure-prerequisites)
10. [Entra External ID setup](#10-entra-external-id-setup)
11. [Azure infrastructure deployment](#11-azure-infrastructure-deployment)
12. [Application deployment](#12-application-deployment)
13. [Enabling OCR](#13-enabling-ocr)
14. [Granting the admin role](#14-granting-the-admin-role)
15. [Troubleshooting](#15-troubleshooting)
16. [Documentation](#16-documentation)

Commands are given for **Bash** (Linux, macOS, Git Bash/WSL on Windows) and **Windows
PowerShell** wherever the two differ. Where only one block is shown, it works in both.

## 1. Architecture

```text
                              USERS (doctors, admins)
                                       │ HTTPS
                                       ▼
                      ┌─────────────────────────────────┐        ┌───────────────────────┐
                      │ Azure Static Web Apps (Standard)│        │ Microsoft Entra       │
                      │ React + TypeScript + Vite       │        │ External ID tenant    │
                      │ Tailwind, Arabic RTL            │        │ sign-up / sign-in,    │
                      │ /api/* ── linked backend ──┐    │        │ MFA for admins        │
                      └────────────────────────────┼────┘        └──────────▲────────────┘
                                 same-origin proxy │                        │ OIDC code flow
                                                   ▼                        │ + PKCE (BFF)
                      ┌─────────────────────────────────────────────────────┴──┐
                      │ Azure Container Apps: Django 5 + DRF + Gunicorn        │
                      │ HttpOnly session cookie · CSRF · scales 0/1 → N        │
                      │ jobs: migrate (once per deployment) · cleanup (nightly) │
                      └──┬──────────┬───────────┬────────────┬───────────┬─────┘
                         │          │           │            │           │  one user-assigned
                         ▼          ▼           ▼            ▼           ▼  managed identity
                   PostgreSQL    Blob Storage  Key Vault   Azure OpenAI  Application Insights
                   Flexible 16   (private,     (secrets)   (OCR, off by  + Log Analytics
                   Entra auth,   no shared                 default)
                   TLS, PITR     keys, SAS ≤5m)

   GitHub Actions (OIDC, no stored Azure secrets)
     ├─ frontend.yml       → Static Web Apps
     ├─ backend.yml        → Container Registry → migrate job → new Container App revision
     ├─ infrastructure.yml → Bicep what-if / deploy (prod needs approval)
     └─ e2e.yml            → docker compose + Playwright
```

Key decisions: the browser talks to **one origin** (the Static Web App proxies `/api` to Django),
so the session cookie is first-party; Django is a confidential OIDC client (BFF) and the browser
never holds a token; **the server is authoritative** for fees, validation, document rules and
status transitions; documents live only in a private Blob container; OCR runs only on the server.
Mermaid diagrams: [`docs/architecture.md`](docs/architecture.md). Data model:
[`docs/database.md`](docs/database.md).

## 2. Repository layout

```text
backend/            Django 5.2 + DRF, Python 3.12, PostgreSQL (psycopg 3), Gunicorn
  apps/             accounts · doctors · applications · beneficiaries · documents · fees · ocr · reference · audit · common
  config/           settings/{base,development,test,production}.py, Entra DB backend, telemetry, logging
  Dockerfile        multi-stage: `dev` (compose) and `runtime` (Container Apps, non-root, Gunicorn)
  entrypoint.sh     modes: web | migrate | cleanup | any other command (compose: migrate + seed, then runserver)
frontend/           React 19 + TypeScript (strict) + Vite + Tailwind 4, React Router, TanStack Query
  src/i18n/ar.ts    every UI string
  e2e/              Playwright specs
  public/staticwebapp.config.json   SWA routes, CSP and security headers
infrastructure/     main.bicep, 14 modules, parameters/{dev,staging,prod}.bicepparam, scripts/
.github/workflows/  frontend.yml, backend.yml, infrastructure.yml, e2e.yml, reusable-*.yml
docs/               architecture, database, api, business rules, deployment, Entra, GitHub, security, OCR, local dev
docker-compose.yml  PostgreSQL 16 + Azurite + Django (development settings)
package.json, Makefile   the same local shortcuts (npm run <x> / make <x>)
.env.example        variable NAMES only
```

## 3. Local setup

Prerequisites: **Docker Desktop** (or Docker Engine with Compose v2), **Node.js 22 LTS** with npm,
**Git**. Python is not needed on the host (Django runs in a container); install Python 3.12 only
to run Django on the host (`docs/local-development.md`). No Azure account or Entra tenant is
needed locally: development settings enable the dev sign-in and the mock OCR provider.

Bash:

```bash
git clone <repository-url> medical-syndicates && cd medical-syndicates
docker compose up -d --build                  # PostgreSQL 16, Azurite, Django :8000 (migrates + seeds on start)
docker compose ps                              # postgres, azurite, backend: (healthy)
curl http://localhost:8000/api/ready/          # {"status": "ok", "database": "ok"}
cd frontend && npm ci && npm run dev           # http://localhost:5173
```

Windows PowerShell:

```powershell
git clone <repository-url> medical-syndicates; Set-Location medical-syndicates
docker compose up -d --build
docker compose ps
curl.exe http://localhost:8000/api/ready/      # curl.exe: plain `curl` is Invoke-WebRequest in PowerShell 5.1
Set-Location frontend; npm ci; npm run dev
```

Open **http://localhost:5173** → `تسجيل الدخول` → pick a seeded user in the development sign-in
panel. Vite proxies `/api` to Django, so cookies behave as in production (same origin).

| User | Role | Seeded state |
|---|---|---|
| `admin@dev.local` | ADMIN | — |
| `doctor@dev.local` | DOCTOR | worked example 2 (wife, son, daughter), **SUBMITTED**, receipt pending, 3٬025 ج.م |
| `doctor2@dev.local` | DOCTOR | female member + mother, **NEEDS_CORRECTION** with review notes |
| `new.doctor@dev.local` | DOCTOR | empty profile (first sign-in experience) |

Shortcuts (root `package.json`; `make <name>` does the same where `make` exists):
`npm run up | down | logs | migrate | makemigrations | seed | test | test:backend | test:frontend | lint | dev | e2e | ci`.

Stop: `docker compose down` (data kept). Reset everything: `docker compose down -v`.

Port already taken? Put overrides in a root `.env` (gitignored), e.g. `AZURITE_BLOB_PORT=10100`.
More (host-run Django, ports, fresh throwaway stack, production image locally):
[`docs/local-development.md`](docs/local-development.md).

## 4. Environment variables

`.env.example` lists every name with no values. Locally nothing is required: docker compose and
development settings supply working defaults, and a root `.env` holds only your overrides (empty
values are ignored, so a copy of `.env.example` is harmless). In Azure every value is set by
`infrastructure/main.bicep` on the Container App and both jobs; secrets are Key Vault references.
Production settings **refuse to start** when a required value is missing or unsafe.

**docker compose (local only)**

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `medical` | credentials of the local PostgreSQL container (never used in Azure) |
| `POSTGRES_PORT`, `AZURITE_BLOB_PORT`, `BACKEND_PORT` | 5432, 10000, 8000 | host ports |
| `RUN_MIGRATIONS_ON_START`, `SEED_ON_START` | `true` | the compose container migrates and seeds on start (refused in `web` mode, i.e. in Azure) |
| `AZURITE_BLOB_HOST` | `azurite` in compose, `127.0.0.1` on the host | where development settings find the emulator |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | where Vite proxies `/api` |
| `E2E_BASE_URL` | `http://localhost:5173` | Playwright base URL |

**Django core**

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.development` (compose), `config.settings.production` (image) | settings module; `config.settings.test` for pytest |
| `DJANGO_SECRET_KEY` | dev placeholder | signing key; production requires ≥ 50 chars, from Key Vault `django-secret-key` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma list; production: Container App FQDN + public host, never `*` |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:5173` | origins allowed to POST; production: `https://<public host>` |
| `TRUSTED_PROXY_COUNT` | 0 (2 in production) | how many `X-Forwarded-For` entries the proxies add (SWA linked backend + ingress); used for throttles and the audit IP hash |
| `DEBUG` | `false` | production refuses `true` |
| `LOG_LEVEL` | `INFO` | JSON logs to stdout; national IDs always masked |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_PRELOAD` | `true` (production) | HTTPS redirect, HSTS preload flag |

**Database**

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | compose PostgreSQL | `postgres://<user>@<host>:5432/<db>`; in Azure the user is the managed identity's role |
| `DB_SSLMODE` | `prefer` (dev), `require` (production) | production refuses anything below `require` |
| `DB_CONN_MAX_AGE` | 60 | persistent connection seconds (capped at 1800 with Entra tokens) |
| `DB_AUTH_MODE` | `entra` (production) | `entra` = managed-identity access token per connection; `password` = fallback |
| `DATABASE_PASSWORD` | — | only with `DB_AUTH_MODE=password` (Key Vault `database-password`) |

**Azure identity, Key Vault, telemetry, Gunicorn**

| Variable | Meaning |
|---|---|
| `AZURE_CLIENT_ID` | client id of the user-assigned managed identity (set by Bicep). A wrong value = token errors with PostgreSQL, Blob, Key Vault |
| `AZURE_TOKEN_CREDENTIALS` | `prod` in Azure: `DefaultAzureCredential` uses only managed-identity/workload credentials |
| `KEY_VAULT_URL` | secrets missing from the environment are read here (`django-secret-key`, `entra-client-secret`, `database-password`) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | enables OpenTelemetry export (Key Vault reference in Azure); empty = no export |
| `APPLICATIONINSIGHTS_AUTHENTICATION` | `entra` = ingestion authenticated with the managed identity |
| `OTEL_SERVICE_NAME` | cloud role name in Application Insights (Bicep: `medical-backend`, `medical-migrate`, `medical-cleanup`) |
| `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT` | 3, 1, 60 s (Bicep sets workers per environment) |

**Business configuration** ([`docs/business-rules.md`](docs/business-rules.md) §10)

| Variable | Default | Meaning |
|---|---|---|
| `CURRENT_FISCAL_YEAR` | 2026 | fiscal year of new applications and fee quotes |
| `MAX_BENEFICIARIES` | 10 | beneficiaries per application |
| `REQUIRE_MEMBER_PHOTO` | `false` | personal photo mandatory |
| `CHILD_NATIONAL_ID_AGE` | 16 | children from this age need a national ID instead of a birth certificate |
| `ENFORCE_SPOUSE_GENDER` | `true` | WIFE needs a male member, HUSBAND a female member |
| `ENFORCE_SON_MINOR_AGE`, `SON_MINOR_MAX_AGE` | `true`, 18 | SON_MINOR age limit |

**Feature flags, sessions, rate limits**

| Variable | Default | Meaning |
|---|---|---|
| `DEV_AUTH_ENABLED` | `true` dev, `false` prod | development sign-in; production refuses to start when `true` |
| `API_DOCS_ENABLED` | `true` dev, `false` prod | `/api/schema/` and `/api/docs/` |
| `OCR_ENABLED` | `true` dev, `false` prod | shows `مسح تلقائي` and enables `/documents/{id}/extract/` |
| `OCR_PROVIDER` | `mock` | `mock` (dev/tests) or `azure_openai` (production; `mock` refused) |
| `OCR_RATE_LIMIT`, `UPLOAD_RATE_LIMIT`, `AUTH_CALLBACK_RATE_LIMIT` | `30/hour`, `60/hour`, `20/min` | per user (OCR, uploads) / per client address (sign-in callback) |
| `SESSION_IDLE_TIMEOUT_SECONDS`, `SESSION_ABSOLUTE_TIMEOUT_SECONDS` | 7200, 43200 | session idle and absolute lifetime |
| `CACHE_URL` | `locmemcache://` (Azure: `dbcache://django_cache`) | rate-limit counters; must be shared when there is more than one replica |

**Documents / Blob Storage**

| Variable | Default | Meaning |
|---|---|---|
| `BLOB_BACKEND` | `azure` | `azure` (Azurite locally) or `memory` (tests only; refused in production) |
| `BLOB_CONNECTION_STRING` | Azurite string in development | local only; production refuses account keys (except the Azurite emulator string) |
| `BLOB_ACCOUNT_URL` | — | `https://<account>.blob.core.windows.net/` (managed identity) |
| `BLOB_CONTAINER` | `medical-documents` | private container |
| `BLOB_CREATE_CONTAINER` | `true` dev, `false` prod | create the container on first use (Bicep creates it in Azure) |
| `DOCUMENT_CONTENT_DELIVERY` | `stream` | `stream` = Django streams the bytes after authorization; `sas` = 302 to a read-only SAS |
| `BLOB_SAS_TTL_SECONDS` | 300 | SAS lifetime, capped at 300 |
| `BLOB_CLEANUP_GRACE_HOURS` | 24 | the cleanup job purges orphan / soft-deleted blobs older than this |
| `MAX_UPLOAD_BYTES` | 8388608 | 8 MB per file (bigger requests get 413 before the body is read) |
| `DOCUMENT_MAX_PIXELS` | 40000000 | decompression-bomb cap |
| `ALLOW_PDF_DOCUMENTS`, `ALLOW_HEIC` | `false` | extra upload types |
| `MALWARE_SCAN_ENABLED` | `false` | reserved for Defender for Storage malware scanning (decision L8) |

**Azure OpenAI and Microsoft Entra External ID**

| Variable | Meaning |
|---|---|
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` | OCR provider (all three required when `OCR_ENABLED` with `azure_openai`); no API key exists |
| `ENTRA_AUTHORITY` | `https://<tenant>.ciamlogin.com/<tenant-id>` |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | external tenant and app registration (printed by `create-entra-app`) |
| `ENTRA_CLIENT_SECRET` | confidential-client secret, Key Vault `entra-client-secret` |
| `ENTRA_REDIRECT_URI` | `https://<public host>/api/v1/auth/callback/` |
| `ENTRA_POST_LOGOUT_REDIRECT_URI` | `https://<public host>/signed-out` |
| `ENTRA_SCOPES` | extra scopes (empty; `openid profile` are always requested) |
| `ENTRA_ADMIN_REQUIRE_MFA` | `true`: refuse an admin session whose ID token lacks `mfa` in `amr` |
| `ENTRA_ISSUER`, `ENTRA_JWKS_URI` | optional overrides of the values from OIDC discovery |

## 5. Database migrations

```bash
npm run makemigrations             # = docker compose exec backend python manage.py makemigrations
npm run migrate                    # = docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run   # nothing missing
```

In Azure, migrations run **exactly once per deployment** in the Container Apps job `migrate`
(`entrypoint.sh migrate` → `migrate --noinput` + `createcachetable`) before the new revision gets
traffic; replicas never migrate. Migrations must be backward compatible (expand/contract).
Procedure and rollback: [`docs/database.md`](docs/database.md) §6 and
[`docs/azure-deployment.md`](docs/azure-deployment.md) *Deployment-time migrations*.

## 6. Seeding

```bash
npm run seed                       # = docker compose exec backend python manage.py seed_dev_data
```

Idempotent. Creates the FY 2026 fee schedule if missing (the migration `fees.0002_seed_fy2026`
already creates it everywhere, including Azure), one admin and three doctors (two with sample
applications in different statuses, real PNG documents in Azurite). `seed_dev_data` refuses to run
without `DEV_AUTH_ENABLED`, so it can never seed production.

## 7. Running tests

With the stack up (`npm run up`):

| What | Command | Last result (2026-10-06) |
|---|---|---|
| Backend: ruff, system check, migration check, pytest on PostgreSQL (+ Azurite) | `npm run lint:backend` and `npm run test:backend` | ruff clean; **964 passed, 1 skipped** (the skipped test reads the repository-root `.env.example`, which the container does not mount; it passes on the host and in CI) |
| Frontend: ESLint, `tsc`, Vitest, `rtl_check.py`, production build | `cd frontend && npm run ci` | **281 passed**; RTL 0 errors / 0 warnings |
| End-to-end (Playwright: doctor submit, admin approve, correction loop, A4 print, 390 px phone) | `cd frontend && npx playwright install chromium` (once), then `npx playwright test` | **11 passed, 5 skipped** (each spec runs in its own viewport project) |
| Everything except e2e | `npm run ci` | |

PowerShell: identical commands; replace `&&` with `;` (Windows PowerShell 5.1), e.g.
`Set-Location frontend; npm run ci; npx playwright test`.

Host-run pytest (no container): `cd backend && .venv/Scripts/python -m pytest -q` (Windows) or
`.venv/bin/python -m pytest -q`, with PostgreSQL from compose on `localhost:5432`.

The full verification record (`manage.py check --deploy` with the production environment, clean
migration run, image build, Bicep, actionlint, gitleaks, dependency audits) is in
[`docs/verification.md`](docs/verification.md).

## 8. Docker

| Image / stage | Use |
|---|---|
| `backend/Dockerfile` target `dev` | docker compose (`runserver`, code mounted) |
| `backend/Dockerfile` target `runtime` | Container Apps: Python 3.12 slim, multi-stage, non-root uid 10001, Gunicorn, `collectstatic` at build, health check on `/api/health/`, no state |

```bash
docker build --target runtime -t medical-backend:runtime backend/
# entrypoint modes (same image for the app and both jobs):
docker run -d --name medical-prod --network medical-syndicates_default --env-file prodlike.env -p 8010:8000   medical-backend:runtime                                             # web: Gunicorn, never migrates
docker run --rm --network medical-syndicates_default --env-file prodlike.env medical-backend:runtime migrate
docker run --rm --network medical-syndicates_default --env-file prodlike.env medical-backend:runtime cleanup --dry-run
```

`prodlike.env` (never commit it) and the full local production run against the compose
PostgreSQL with TLS: [`docs/local-development.md`](docs/local-development.md) *Running the
production image locally*. The frontend is not containerized: it is a static build
(`frontend/dist`) deployed to Static Web Apps. PostgreSQL never runs in a container in Azure.

## 9. Azure prerequisites

- Azure CLI ≥ 2.60 with Bicep (`az bicep install`), Docker, Node 22, `psql` ≥ 15, Git Bash or WSL
  on Windows for the `.sh` scripts (the Entra and GitHub scripts also exist as `.ps1`).
- A subscription where you are **Owner** (or Contributor + User Access Administrator) on the
  target resource group, and whose Azure Policy allows the chosen region **and** a Static Web
  Apps region (`westeurope`, `centralus`, `eastus2`, `westus2`, `eastasia`).
- An **Entra External ID** (external) tenant for sign-in, separate from the workforce tenant.
- The legal decision on the data region (L3) and on OCR (L2) — [`docs/security.md`](docs/security.md) §6.
- Resource providers registered once per subscription:

```bash
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL Microsoft.KeyVault \
          Microsoft.Storage Microsoft.Web Microsoft.OperationalInsights Microsoft.Insights \
          Microsoft.ManagedIdentity Microsoft.CognitiveServices Microsoft.Network; do
  az provider register --namespace "$ns"
done
```

```powershell
foreach ($ns in 'Microsoft.App','Microsoft.ContainerRegistry','Microsoft.DBforPostgreSQL','Microsoft.KeyVault',
                'Microsoft.Storage','Microsoft.Web','Microsoft.OperationalInsights','Microsoft.Insights',
                'Microsoft.ManagedIdentity','Microsoft.CognitiveServices','Microsoft.Network') {
  az provider register --namespace $ns
}
```

## 10. Entra External ID setup

Full steps: [`docs/entra-setup.md`](docs/entra-setup.md). In short: create the external tenant,
a sign-up/sign-in user flow with Arabic enabled, then one app registration per environment with
the script (Web platform, code flow only, redirect URIs, `email` optional claim, client secret
written straight to Key Vault and never printed):

```bash
az login --tenant <workforce-tenant-id>
az login --tenant <external-tenant-id> --allow-no-subscriptions
infrastructure/scripts/create-entra-app.sh --environment dev --tenant-id <external-tenant-id> \
  --public-url "https://$SWA_HOST" --key-vault "$KV" --subscription <subscription-id> \
  --user-flow-id <user-flow-id>
```

```powershell
az login --tenant <workforce-tenant-id>
az login --tenant <external-tenant-id> --allow-no-subscriptions
./infrastructure/scripts/create-entra-app.ps1 -Environment dev -TenantId <external-tenant-id> `
  -PublicUrl "https://$SWA_HOST" -KeyVault $KV -Subscription <subscription-id> -UserFlowId <user-flow-id>
```

`$SWA_HOST` and `$KV` come from the first infrastructure phase (§11 step 3); run this between
step 4 and step 6. Add `--local` / `-Local` for a dev registration that also accepts
`http://localhost:5173`. Then require MFA for the `medical-admins-<env>` group with a Conditional
Access policy (`docs/entra-setup.md` §4).

## 11. Azure infrastructure deployment

Two phases, because Container Apps resolve Key Vault references when they are created: first
everything except the application, then secrets, Entra and the database role, then the app.
Details and reasons for each step: [`docs/azure-deployment.md`](docs/azure-deployment.md).
CI/CD does the same through OIDC once set up ([`docs/github-setup.md`](docs/github-setup.md)).

**Bash**

```bash
# 1. Resource group
az login && az account set --subscription <subscription-id>
ENV=dev; RG=rg-medsyn-$ENV; LOCATION=<region>
az group create --name "$RG" --location "$LOCATION" --tags application=medical-syndicates environment=$ENV

# 2. Values read by infrastructure/parameters/$ENV.bicepparam (never committed)
export KEY_VAULT_OPERATOR_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv)" KEY_VAULT_OPERATOR_TYPE=User
unset CONTAINER_IMAGE                      # first phase: no Container App yet

# 3. First phase
az deployment group what-if -g "$RG" -n "main-$ENV" -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"
az deployment group create  -g "$RG" -n "main-$ENV" -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"
out() { az deployment group show -g "$RG" -n "main-$ENV" --query "properties.outputs.$1.value" -o tsv; }
KV=$(out keyVaultName); ACR=$(out containerRegistryName); PG=$(out postgresServerName)
IDENTITY=$(out identityName); SWA_HOST=$(out staticWebAppHostname)

# 4. Django secret key into Key Vault (never echoed)
tmp=$(mktemp) && chmod 600 "$tmp"
python -c "import secrets; print(secrets.token_urlsafe(64), end='')" > "$tmp"
az keyvault secret set --vault-name "$KV" --name django-secret-key --file "$tmp" --output none; rm -f "$tmp"

# 5. Entra app registration (section 10), then:
export ENTRA_AUTHORITY=https://<tenant-subdomain>.ciamlogin.com/<external-tenant-id>
export ENTRA_TENANT_ID=<external-tenant-id> ENTRA_CLIENT_ID=<application-client-id>

# 6. PostgreSQL Entra admin, database and the managed identity's role
infrastructure/scripts/setup-postgres-entra.sh --resource-group "$RG" --server "$PG" \
  --identity-name "$IDENTITY" --database medical --allow-current-ip
```

**Windows PowerShell**

```powershell
# 1. Resource group
az login; az account set --subscription <subscription-id>
$EnvName = "dev"; $RG = "rg-medsyn-$EnvName"; $Location = "<region>"
az group create --name $RG --location $Location --tags application=medical-syndicates environment=$EnvName

# 2. Values read by the .bicepparam file
$env:KEY_VAULT_OPERATOR_OBJECT_ID = az ad signed-in-user show --query id -o tsv
$env:KEY_VAULT_OPERATOR_TYPE = "User"
Remove-Item Env:CONTAINER_IMAGE -ErrorAction SilentlyContinue

# 3. First phase
az deployment group what-if -g $RG -n "main-$EnvName" -f infrastructure/main.bicep -p "infrastructure/parameters/$EnvName.bicepparam"
az deployment group create  -g $RG -n "main-$EnvName" -f infrastructure/main.bicep -p "infrastructure/parameters/$EnvName.bicepparam"
function Get-Out($Name) { az deployment group show -g $RG -n "main-$EnvName" --query "properties.outputs.$Name.value" -o tsv }
$KV = Get-Out keyVaultName; $ACR = Get-Out containerRegistryName; $PG = Get-Out postgresServerName
$IDENTITY = Get-Out identityName; $SWA_HOST = Get-Out staticWebAppHostname

# 4. Django secret key into Key Vault (written to a temp file, never echoed)
$tmp = New-TemporaryFile
python -c "import secrets,sys; open(sys.argv[1],'w').write(secrets.token_urlsafe(64))" $tmp.FullName
az keyvault secret set --vault-name $KV --name django-secret-key --file $tmp.FullName --output none
Remove-Item $tmp

# 5. Entra app registration (section 10), then:
$env:ENTRA_AUTHORITY = "https://<tenant-subdomain>.ciamlogin.com/<external-tenant-id>"
$env:ENTRA_TENANT_ID = "<external-tenant-id>"; $env:ENTRA_CLIENT_ID = "<application-client-id>"

# 6. PostgreSQL Entra admin, database and role (bash script: run it in Git Bash or WSL)
bash infrastructure/scripts/setup-postgres-entra.sh --resource-group $RG --server $PG `
  --identity-name $IDENTITY --database medical --allow-current-ip
```

Production: decide `ENABLE_PRIVATE_NETWORKING` **before** the first `prod` deployment (PostgreSQL
networking cannot be changed later; recommended `true`, see `docs/security.md` §7).

## 12. Application deployment

Second phase (first creation of the Container App), continuing in the same shell:

```bash
LOGIN_SERVER=$(az acr show -n "$ACR" --query loginServer -o tsv); TAG=$(git rev-parse HEAD)
docker build --target runtime -t "$LOGIN_SERVER/medical-backend:$TAG" backend/
az acr login -n "$ACR" && docker push "$LOGIN_SERVER/medical-backend:$TAG"
export CONTAINER_IMAGE="$LOGIN_SERVER/medical-backend:$TAG"      # → deployApplication=true
az deployment group create -g "$RG" -n "main-$ENV" -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"

APP=$(out containerAppName); MIGRATE=$(out migrateJobName)
EXEC=$(az containerapp job start -n "$MIGRATE" -g "$RG" --query name -o tsv)
until s=$(az containerapp job execution show -n "$MIGRATE" -g "$RG" --job-execution-name "$EXEC" --query properties.status -o tsv); \
      [ "$s" = Succeeded ] || [ "$s" = Failed ]; do sleep 10; done; echo "migrate: $s"
curl -fsS "https://$(out containerAppFqdn)/api/ready/"

cd frontend && npm ci && npm run build && cd ..
TOKEN=$(az staticwebapp secrets list -n "$(out staticWebAppName)" -g "$RG" --query properties.apiKey -o tsv)
npx --yes @azure/static-web-apps-cli@2 deploy frontend/dist --deployment-token "$TOKEN" --env production; unset TOKEN
```

```powershell
$LoginServer = az acr show -n $ACR --query loginServer -o tsv; $Tag = git rev-parse HEAD
docker build --target runtime -t "$LoginServer/medical-backend:$Tag" backend/
az acr login -n $ACR; docker push "$LoginServer/medical-backend:$Tag"
$env:CONTAINER_IMAGE = "$LoginServer/medical-backend:$Tag"
az deployment group create -g $RG -n "main-$EnvName" -f infrastructure/main.bicep -p "infrastructure/parameters/$EnvName.bicepparam"

$APP = Get-Out containerAppName; $MIGRATE = Get-Out migrateJobName
$Exec = az containerapp job start -n $MIGRATE -g $RG --query name -o tsv
do { Start-Sleep -Seconds 10; $s = az containerapp job execution show -n $MIGRATE -g $RG --job-execution-name $Exec --query properties.status -o tsv } while ($s -notin 'Succeeded','Failed')
"migrate: $s"
curl.exe -fsS "https://$(Get-Out containerAppFqdn)/api/ready/"

Set-Location frontend; npm ci; npm run build; Set-Location ..
$Token = az staticwebapp secrets list -n (Get-Out staticWebAppName) -g $RG --query properties.apiKey -o tsv
npx --yes @azure/static-web-apps-cli@2 deploy frontend/dist --deployment-token $Token --env production; Remove-Variable Token
```

Open `https://$SWA_HOST/`, sign in once, then grant the first administrator (§14).

From then on, **every push to `main`** deploys through GitHub Actions: `backend.yml` builds the
image once, pushes it to each environment's registry, runs the `migrate` job, updates the cleanup
job, creates a new revision and smoke-tests it; `frontend.yml` builds and deploys the SPA;
`infrastructure.yml` runs what-if and deploys Bicep (prod waits for a reviewer). Setup (GitHub
environments, OIDC identities, variables, branch protection): [`docs/github-setup.md`](docs/github-setup.md).

Rollback: `az containerapp update -n "$APP" -g "$RG" --image <previous-image>` (migrations are
expand/contract, so the previous image runs on the newer schema). Backups and restore:
[`docs/azure-deployment.md`](docs/azure-deployment.md) *Backups and recovery*.

## 13. Enabling OCR

Only after the legal decisions L2 (identity documents processed by an AI service) and L3
(region). Locally the mock provider is always on.

```bash
export ENABLE_OCR=true                     # GitHub: environment variable ENABLE_OCR=true
az deployment group create -g "$RG" -n "main-$ENV" -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"
```

```powershell
$env:ENABLE_OCR = "true"
az deployment group create -g $RG -n "main-$EnvName" -f infrastructure/main.bicep -p "infrastructure/parameters/$EnvName.bicepparam"
```

This deploys Azure OpenAI with key authentication disabled and a vision model deployment, grants
the identity *Cognitive Services OpenAI User*, and sets `OCR_ENABLED=true`,
`OCR_PROVIDER=azure_openai`, `AZURE_OPENAI_*`. Check model availability and quota first:
`az cognitiveservices model list -l <region> -o table`. Prompts, privacy and limits:
[`docs/ocr.md`](docs/ocr.md).

## 14. Granting the admin role

The user must have signed in once (the account is created at first sign-in). The grant is
audited (`ADMIN_ROLE_GRANTED`) and ends the user's open sessions, so the next sign-in goes
through the admin MFA check.

```bash
# local
docker compose exec backend python manage.py grant_admin <email-or-entra-oid>
# Azure
az containerapp exec -n "$APP" -g "$RG" --command "python manage.py grant_admin <email-or-entra-oid>"
```

```powershell
az containerapp exec -n $APP -g $RG --command "python manage.py grant_admin <email-or-entra-oid>"
```

Also add the person to the Entra group `medical-admins-<env>` (Conditional Access MFA). There is no
self-service path to the admin role, and the SPA has no admin-granting screen.

## 15. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Signed in, but every API call is 401 / cookies not sent | The SPA and `/api` are on different sites (third-party cookies are blocked). Use the SWA URL (linked backend, `static-web-app-link.bicep`) or the Vite dev server locally — never call the Container App FQDN from the SPA. |
| `403 PERMISSION_DENIED` on POST/PATCH (CSRF) | The page origin is not in `CSRF_TRUSTED_ORIGINS` (custom domain: set `PUBLIC_HOSTNAME` and redeploy), or the `csrftoken` cookie is missing — load `/api/v1/auth/me/` first (the SPA does). |
| Entra `AADSTS50011` redirect URI mismatch | The host is not registered: re-run `create-entra-app` with that `--public-url`; `ENTRA_REDIRECT_URI` must end with `/api/v1/auth/callback/`. |
| `?auth_error=MFA_REQUIRED` for an admin | The ID token has no `mfa` in `amr`: add the user to `medical-admins-<env>` with the Conditional Access policy, or set `entraAdminRequireMfa=false` if the tenant never emits `amr`. |
| PostgreSQL `password authentication failed for user "id-medsyn-<env>"` / managed identity token errors | `setup-postgres-entra.sh` not run, or `AZURE_CLIENT_ID` is not the user-assigned identity's **client id** (Bicep sets it; check `az containerapp show … --query "properties.template.containers[0].env"`), or a token for the wrong tenant. |
| Blob `403 AuthorizationPermissionMismatch` | Role assignment not propagated yet (wait minutes), or `BLOB_ACCOUNT_URL` points at another account. Shared keys are disabled on purpose; do not enable them. SAS links failing: *Storage Blob Delegator* missing on the account. |
| OCR answers `503 OCR_UNAVAILABLE` | OCR disabled, PDF document, model deployment missing, quota exhausted (Azure OpenAI `429` — raise `openAiCapacity` or wait), or *Cognitive Services OpenAI User* not propagated. Per-user limit: `429 RATE_LIMITED` after 30 calls/hour. |
| Revision never ready, logs show `ImproperlyConfigured` | A required production setting is missing or unsafe (secrets, `ENTRA_*`, `DEV_AUTH_ENABLED`). Production refuses to start on purpose. |
| `DisallowedHost` behind the linked backend | The Host Django sees is not in `ALLOWED_HOSTS` (Q-T13): add it through `publicHostname` / `allowedHosts` in `main.bicep`. |
| Local: `port is already allocated` | Put `POSTGRES_PORT`, `AZURITE_BLOB_PORT` or `BACKEND_PORT` in the root `.env`. |
| Local: uploads fail | `docker compose ps azurite` must be healthy. |
| Local: backend tests pick development settings | Use `npm run test:backend` (passes `--ds=config.settings.test`). |

More: [`docs/azure-deployment.md`](docs/azure-deployment.md), [`docs/entra-setup.md`](docs/entra-setup.md),
[`docs/github-setup.md`](docs/github-setup.md), [`docs/local-development.md`](docs/local-development.md).

## 16. Documentation

| File | Content |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Azure architecture, layers, request flows, scaling, pipeline (Mermaid) |
| [`docs/database.md`](docs/database.md) | ER diagram (Mermaid), constraints, indexes, migrations |
| [`docs/api.md`](docs/api.md) | endpoints, error codes, link to the OpenAPI schema |
| [`docs/business-rules.md`](docs/business-rules.md) | fees, national ID, kinships, documents, statuses, open business questions |
| [`docs/azure-deployment.md`](docs/azure-deployment.md) | deployment steps, migrations, rollback, backups and restore, cost |
| [`docs/entra-setup.md`](docs/entra-setup.md) | External ID tenant, user flow, app registration, admin MFA |
| [`docs/github-setup.md`](docs/github-setup.md) | GitHub environments, OIDC, variables, branch protection |
| [`docs/security.md`](docs/security.md) | controls, legal decisions, security review |
| [`docs/ocr.md`](docs/ocr.md) | OCR flow, provider, privacy |
| [`docs/local-development.md`](docs/local-development.md) | local stack, scripts, e2e, production image locally |
| [`docs/verification.md`](docs/verification.md) | PROMPT.md §55 checklist with evidence |
| [`docs/final-report.md`](docs/final-report.md) | PROMPT.md §56 final report |
| [`docs/plan.md`](docs/plan.md), [`docs/progress.md`](docs/progress.md) | implementation plan and session log |
