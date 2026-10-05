# local-development

> The full guide (compose backend service, Makefile, seed scripts) is written in Session 6
> (docs/plan.md). Until then, `docs/progress.md` → "Next session starts with" has the backend
> commands. This page covers the frontend added in Session 4.

## Frontend (`frontend/`)

Node 22 LTS. The SPA calls the API same-origin (`/api`); Vite proxies it to Django on
`http://127.0.0.1:8000` (override with `VITE_API_PROXY_TARGET`).

```bash
cd frontend
npm ci
npm run dev          # http://localhost:5173 — needs runserver with development settings
```

With `DEV_AUTH_ENABLED` (development settings) the landing page shows a dev-login panel listing the
`seed_dev_data` users. It is compiled out of production builds and hidden when the backend answers 404.

| Command | What it runs |
|---|---|
| `npm run lint` | ESLint (incl. a rule refusing physical `ml-/mr-/left-/right-/text-left…` classes) |
| `npm run typecheck` | `tsc --noEmit` for `src/` and for the Node-side files |
| `npm test` | Vitest + Testing Library + MSW (no backend needed) |
| `npm run test:e2e` | Playwright, desktop and 390×844 mobile, against `npm run dev` + the dev backend |
| `npm run rtl:check` | `python scripts/rtl_check.py src` (vendored from the `rtl-ui` skill) |
| `npm run build` | type-check, then the production bundle in `dist/` |
| `npm run ci` | all of the above except e2e |
| `npm run gen:api` | regenerate `src/api/schema.d.ts` from `backend/openapi.yaml` |

Regenerate the API types after a backend serializer change:

```bash
cd backend && python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
cd ../frontend && npm run gen:api
```

Playwright needs a browser once per machine: `npx playwright install chromium`.
