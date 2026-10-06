# Local development

Everything runs locally with Docker Desktop and Node 22: PostgreSQL, Azurite (the Blob Storage
emulator) and Django in `docker compose`, and the React SPA with Vite on the host
(PROMPT.md §32). No Azure account and no Entra tenant are needed: development settings turn on the
dev sign-in (`DEV_AUTH_ENABLED`) and the deterministic mock OCR provider.

```text
 browser ──► Vite :5173 ──/api──► Django :8000 (container, runserver, development settings)
                                     ├─► PostgreSQL 16 :5432 (container, volume pgdata)
                                     └─► Azurite blob :10000 (container, volume azurite-data)
```

## First start

```bash
docker compose up -d --build        # or: npm run up / make up
cd frontend && npm ci && npm run dev
```

Open http://localhost:5173 and pick a user in the dev sign-in panel.

On start the Django container waits for PostgreSQL, applies migrations
(`RUN_MIGRATIONS_ON_START=true`) and runs `seed_dev_data` (`SEED_ON_START=true`). Both are local
conveniences only: in Azure, migrations run once per deployment as a Container Apps job (§37) and
the seed command refuses to run without `DEV_AUTH_ENABLED`.

Check it is up:

```bash
docker compose ps                    # postgres, azurite, backend: (healthy)
curl http://localhost:8000/api/ready/   # {"status": "ok", "database": "ok"}
```

In Windows PowerShell 5.1 use `curl.exe` (plain `curl` is an alias of `Invoke-WebRequest`) and
`;` instead of `&&`: `Set-Location frontend; npm ci; npm run dev`.

## Seeded data (`seed_dev_data`, idempotent)

| User | Role | Data |
|---|---|---|
| `admin@dev.local` | ADMIN | — |
| `doctor@dev.local` | DOCTOR | worked example 2 (WIFE, SON_MINOR, DAUGHTER), application **SUBMITTED**, receipt waiting for confirmation, 3٬025 ج.م |
| `doctor2@dev.local` | DOCTOR | female member + MOTHER, application **NEEDS_CORRECTION** with review notes from the admin, 2٬075 ج.م |
| `new.doctor@dev.local` | DOCTOR | empty profile, no application (first sign-in experience) |

The FY 2026 fee schedule comes from the `fees` seed migration; the command re-creates it if no
active FY 2026 version exists. Documents are real PNG blobs in Azurite, uploaded through the
document service. National IDs are synthetic.

## Scripts

The root `package.json` (`npm run <name>`) and the `Makefile` (`make <name>`, where `make` exists)
offer the same commands. Docker Desktop must be running.

| npm | make | What it does |
|---|---|---|
| `npm run up` | `make up` | build and start PostgreSQL, Azurite, Django |
| `npm run down` | `make down` | stop the stack (volumes kept; `docker compose down -v` wipes them) |
| `npm run logs` | `make logs` | follow the Django log (JSON lines, national IDs masked) |
| `npm run migrate` | `make migrate` | `manage.py migrate` in the container |
| `npm run makemigrations` | `make makemigrations` | `manage.py makemigrations` in the container |
| `npm run seed` | `make seed` | `manage.py seed_dev_data` |
| `npm run test:backend` | `make test-backend` | pytest in the container with `config.settings.test` (PostgreSQL + Azurite tests) |
| `npm run test:frontend` | `make test-frontend` | Vitest |
| `npm test` | `make test` | both |
| `npm run lint` | `make lint` | ruff check + format check, ESLint, `tsc`, `rtl_check.py` |
| `npm run dev` | `make dev` | Vite on http://localhost:5173 |
| `npm run e2e` | `make e2e` | Playwright against the running stack |
| `npm run ci` | `make ci` | lint, tests, frontend production build |

`test:backend` passes `--ds=config.settings.test` explicitly: the container's
`DJANGO_SETTINGS_MODULE=config.settings.development` would otherwise win over `pyproject.toml`.

## Ports and overrides

Every value can be overridden in a root `.env` (gitignored; `.env.example` lists the names).

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_PORT` | 5432 | host port of PostgreSQL |
| `AZURITE_BLOB_PORT` | 10000 | host port of Azurite (this machine uses 10100, D28). Inside compose Django always reaches `azurite:10000` |
| `BACKEND_PORT` | 8000 | host port of Django; Vite proxies to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8000`) |
| `RUN_MIGRATIONS_ON_START` | true | set `false` to migrate by hand |
| `SEED_ON_START` | true | set `false` to start without sample data |

A second, throwaway stack with empty volumes (useful to check a fresh start without touching your
data):

```bash
POSTGRES_PORT=55432 AZURITE_BLOB_PORT=10210 BACKEND_PORT=8100 docker compose -p medical-fresh up -d
curl http://localhost:8100/api/ready/
POSTGRES_PORT=55432 AZURITE_BLOB_PORT=10210 BACKEND_PORT=8100 docker compose -p medical-fresh down -v
```

```powershell
$env:POSTGRES_PORT = "55432"; $env:AZURITE_BLOB_PORT = "10210"; $env:BACKEND_PORT = "8100"
docker compose -p medical-fresh up -d
curl.exe http://localhost:8100/api/ready/
docker compose -p medical-fresh down -v
Remove-Item Env:POSTGRES_PORT, Env:AZURITE_BLOB_PORT, Env:BACKEND_PORT
```

## Running Django on the host instead

Useful with a debugger. Stop the container (`docker compose stop backend`), then:

```bash
cd backend
uv venv .venv --python 3.12 && uv pip install --python .venv -r requirements/dev.txt
DJANGO_SETTINGS_MODULE=config.settings.development .venv/Scripts/python manage.py migrate
DJANGO_SETTINGS_MODULE=config.settings.development .venv/Scripts/python manage.py runserver 8000
.venv/Scripts/python -m pytest -q        # test settings come from pyproject.toml
```

```powershell
Set-Location backend
uv venv .venv --python 3.12; uv pip install --python .venv -r requirements/dev.txt
$env:DJANGO_SETTINGS_MODULE = "config.settings.development"
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py runserver 8000
Remove-Item Env:DJANGO_SETTINGS_MODULE; .venv\Scripts\python -m pytest -q
```

(`.venv/bin/python` on Linux/macOS.) Development settings read the root `.env` (empty values are
ignored, so a copy of `.env.example` keeps every default), so the host-side Django finds Azurite
on `AZURITE_BLOB_PORT`.

## Frontend (`frontend/`)

| Command | What it runs |
|---|---|
| `npm run lint` | ESLint (incl. a rule refusing physical `ml-/mr-/left-/right-/text-left…` classes) |
| `npm run typecheck` | `tsc --noEmit` for `src/` and for the Node-side files (`e2e/`, configs) |
| `npm test` | Vitest + Testing Library + MSW (no backend needed) |
| `npm run test:e2e` | Playwright against `npm run dev` + the compose backend |
| `npm run rtl:check` | `python scripts/rtl_check.py src` (vendored from the `rtl-ui` skill) |
| `npm run build` | type-check, then the production bundle in `dist/` (admin pages are separate lazy chunks) |
| `npm run ci` | all of the above except e2e |
| `npm run gen:api` | regenerate `src/api/schema.d.ts` from `backend/openapi.yaml` |

Regenerate the API types after a backend serializer change:

```bash
docker compose exec backend python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
cd frontend && npm run gen:api
```

## End-to-end tests (Playwright)

Playwright needs a browser once per machine: `npx playwright install chromium`. With the stack up:

```bash
cd frontend && npx playwright test
```

| Spec | Scenario (PROMPT.md §42) |
|---|---|
| `foundation.spec.ts` | RTL + Cairo, dev login, sign-out, doctor refused from `/admin/*` |
| `doctor-submit.spec.ts` | fresh doctor → OCR → family → 3٬025 ج.م → receipt → submit → reference → A4 PDF ≤ 2 pages |
| `admin-approve.spec.ts` | admin dashboard → filtered list → search → confirm payment → review → approve → doctor sees مقبول; 390 px overflow check |
| `correction-loop.spec.ts` | admin requests a correction (notes required) → doctor fixes and resubmits → same reference number |

Each run creates `e2e-*@dev.local` doctors and submitted applications in the dev database (new
reference numbers each time); `docker compose down -v` resets everything. The doctor and admin
specs run on the desktop project and resize to 390 px themselves.

## Troubleshooting

- **`port is already allocated`** — another process holds 5432/10000/8000: set the matching
  `*_PORT` in `.env`.
- **Uploads fail with a storage error** — `docker compose ps azurite` must be healthy; the
  container `medical-documents` is created on first use.
- **Backend tests use development settings** — run them through `npm run test:backend` (adds
  `--ds=config.settings.test`).

## Running the production image locally

The `runtime` stage of `backend/Dockerfile` is the image deployed to Container Apps. It uses
production settings, which refuse a database connection without TLS, development sign-in, mock
OCR and Blob account keys (the Azurite emulator string is the one exception).

```bash
# once per compose volume: self-signed TLS for the compose PostgreSQL (development stays on sslmode=prefer)
backend/.venv/Scripts/python backend/scripts/local_postgres_tls.py

docker build --target runtime -t medical-backend backend/
# prodlike.env (never commit it): DJANGO_SECRET_KEY=<64 random chars>, ALLOWED_HOSTS=localhost,
#   CSRF_TRUSTED_ORIGINS=https://localhost:8443, DATABASE_URL=postgres://medical:medical@postgres:5432/medical,
#   DB_AUTH_MODE=password, DB_SSLMODE=require, BLOB_CONNECTION_STRING=<Azurite string with host azurite>,
#   ENTRA_AUTHORITY / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET / ENTRA_REDIRECT_URI=<placeholders>
docker run -d --name medical-prod --network medical-syndicates_default --env-file prodlike.env \
  -p 8010:8000 medical-backend            # web mode: Gunicorn, never migrates
curl http://localhost:8010/api/health/    # {"status": "ok"}
curl http://localhost:8010/api/ready/     # {"status": "ok", "database": "ok"}
docker run --rm --network medical-syndicates_default --env-file prodlike.env medical-backend migrate
docker run --rm --network medical-syndicates_default --env-file prodlike.env medical-backend cleanup --dry-run
```

Other API paths answer `301` to HTTPS unless the request carries `X-Forwarded-Proto: https` (as
Container Apps ingress sends it).
