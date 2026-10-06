# GitHub setup (repository, environments, OIDC, variables)

How to connect this repository to GitHub Actions and Azure (PROMPT.md §36). Azure access uses
**GitHub OIDC federated credentials only**: no Azure password, service-principal secret or Static
Web Apps deployment token is stored in GitHub.

> **Nothing in this document has been executed.** No repository was created, nothing was pushed
> and no GitHub setting was changed: each of those steps needs the owner's explicit confirmation.
> Commands are given for the GitHub CLI (`gh` ≥ 2.40); every step can also be done in the web UI.
> **NOT VERIFIED — requires Azure credentials / a GitHub repository.**

## Workflows

| File | Trigger | What it does |
|---|---|---|
| `.github/workflows/frontend.yml` | PR / push to `main` touching `frontend/**` | `npm ci` → lint → type check → Vitest → `rtl_check.py` → build; on `main`: deploy the same build to dev → staging → prod (Static Web Apps) |
| `.github/workflows/backend.yml` | PR / push touching `backend/**` | ruff → `manage.py check` → migrations check → OpenAPI validation → pytest on a `postgres:16` service → build the runtime image once; on `main`: push to each environment's ACR → **run the migrate job** → update the cleanup job → new Container App revision → smoke test |
| `.github/workflows/infrastructure.yml` | PR / push touching `infrastructure/**`, manual | `bicep build` + lint of every file, `build-params`, script checks; PR: **what-if** against dev; `main`: what-if + deploy dev → staging → prod; manual: one environment, optionally what-if only |
| `.github/workflows/e2e.yml` | PR to `main`, manual | fresh docker compose stack (PostgreSQL, Azurite, Django, dev auth, mock OCR) + Azurite pytest + Playwright (desktop and mobile) |
| `reusable-*.yml` | called by the above | per-environment deploy jobs (frontend, backend, infrastructure) |

Every third-party action is pinned to a full commit SHA (tag in a comment). Workflow permissions
default to `contents: read`; only deploy jobs get `id-token: write`.

## 1. Create the repository (owner confirmation required)

```bash
gh repo create <owner>/<repo> --private --source . --remote origin   # creates the repo, no push
git push -u origin main                                              # first push — confirm first
```

## 2. Environments and protection rules

Create `dev`, `staging` and `prod` (Settings → Environments, or):

```bash
gh api -X PUT "repos/<owner>/<repo>/environments/dev"
gh api -X PUT "repos/<owner>/<repo>/environments/staging"
# prod: required reviewers, no self-review, deployments from main only
gh api -X PUT "repos/<owner>/<repo>/environments/prod" --input - <<'JSON'
{
  "reviewers": [{"type": "Team", "id": <team-id>}],
  "prevent_self_review": true,
  "deployment_branch_policy": {"protected_branches": true, "custom_branch_policies": false}
}
JSON
```

(`gh api orgs/<org>/teams/<team-slug> --jq .id` gives the team id; use `{"type": "User", "id": <user-id>}`
for individual reviewers.) Restrict `staging` to protected branches the same way. `dev` stays
unprotected so pull-request what-if can run, but it only ever touches the dev resource group.

## 3. Azure side: OIDC identities (once per environment)

Create the environment's resource group, then run the script (bash or PowerShell). It creates a
user-assigned identity `id-github-medsyn-<env>`, a federated credential for
`repo:<owner>/<repo>:environment:<env>`, and roles on that resource group only:

| Role | Why |
|---|---|
| Contributor | deploy Bicep, update the Container App and jobs, start the migrate job, read the Static Web App deployment token at run time |
| AcrPush | push the backend image to the environment's registry |
| Role Based Access Control Administrator, **condition-restricted** | create/delete only the role assignments `main.bicep` declares (Storage Blob Data Contributor, Storage Blob Delegator, Key Vault Secrets User/Officer, AcrPull, Cognitive Services OpenAI User, Monitoring Metrics Publisher) — it cannot grant Owner or Contributor |

```bash
az login
az account set --subscription <subscription-id>
az group create --name rg-medsyn-dev --location <region> --tags application=medical-syndicates environment=dev
infrastructure/scripts/setup-github-oidc.sh --resource-group rg-medsyn-dev --environment dev --repo <owner>/<repo>
```

```powershell
./infrastructure/scripts/setup-github-oidc.ps1 -ResourceGroup rg-medsyn-dev -Environment dev -Repo <owner>/<repo>
```

Repeat for `staging` and `prod` (separate resource groups, ideally separate subscriptions for
prod, §49). Jobs that do not run in the matching GitHub environment cannot obtain a token for it.

## 4. Environment variables

Settings → Environments → `<env>` → **Environment variables** (none of these is a secret; no
GitHub *secret* is needed at all):

| Variable | Source | Used by |
|---|---|---|
| `AZURE_CLIENT_ID` | printed by `setup-github-oidc` | all deploy jobs (`azure/login`) |
| `AZURE_TENANT_ID` | printed by `setup-github-oidc` | all deploy jobs |
| `AZURE_SUBSCRIPTION_ID` | printed by `setup-github-oidc` | all deploy jobs |
| `AZURE_RESOURCE_GROUP` | your resource group | all deploy jobs |
| `ENTRA_AUTHORITY`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | printed by `create-entra-app` (`docs/entra-setup.md`) | infrastructure (Container App settings) |
| `ACR_NAME` | output `containerRegistryName` | backend |
| `CONTAINER_APP_NAME` | output `containerAppName` | backend, infrastructure (keeps the running image) |
| `MIGRATE_JOB_NAME` | output `migrateJobName` | backend |
| `CLEANUP_JOB_NAME` | output `cleanupJobName` | backend |
| `STATIC_WEB_APP_NAME` | output `staticWebAppName` | frontend |
| `PUBLIC_HOSTNAME` *(optional)* | custom domain bound to the Static Web App | infrastructure |
| `STATIC_WEB_APP_LOCATION` *(optional)* | default `westeurope` | infrastructure |
| `ENABLE_OCR` *(optional)* | `true` only after legal decisions L2/L3 | infrastructure |
| `ENABLE_PRIVATE_NETWORKING` *(optional, prod)* | decide before the first prod deployment | infrastructure |
| `KEY_VAULT_OPERATOR_OBJECT_ID` / `KEY_VAULT_OPERATOR_TYPE` *(optional)* | object id of the person/group who sets Key Vault secrets | infrastructure |
| `POSTGRES_ENTRA_ADMIN_OBJECT_ID` / `_NAME` / `_TYPE` *(optional)* | Entra admin group of the PostgreSQL server | infrastructure |

```bash
gh variable set AZURE_CLIENT_ID --env dev --repo <owner>/<repo> --body <client-id>
# … one line per variable; after the first infrastructure deployment:
az deployment group show -g rg-medsyn-dev -n main-dev --query properties.outputs -o json
```

## 5. Branch protection for `main`

```bash
gh api -X PUT "repos/<owner>/<repo>/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": {"strict": true, "contexts": [
    "lint, type check, test, rtl check, build",
    "ruff, migrations check, pytest",
    "build image",
    "bicep build and lint",
    "playwright"
  ]},
  "enforce_admins": true,
  "required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": true},
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Status checks only appear in the list after they ran once; workflows filtered by `paths` do not
run on every PR, so either keep only the checks that always run or add the path-independent ones
after the first PRs. Also enable: Settings → Actions → General → *Workflow permissions: Read
repository contents*; Settings → Code security → secret scanning and push protection.

## 6. First deployment order

1. `infrastructure.yml` runs on the first push (or manually): with no Container App yet it deploys
   the **first phase** (everything except the app, its jobs and the SWA link).
2. Set the Key Vault secrets, create the Entra app, run `setup-postgres-entra.sh`
   (`docs/azure-deployment.md`, steps 4–6). Fill the variables of section 4.
3. Create the application once by hand (second phase, `docs/azure-deployment.md` step 7: push
   the first image, deploy with `CONTAINER_IMAGE` set). `backend.yml` updates an existing
   Container App, so it cannot do this first creation; from then on every push to `main`
   deploys automatically, and `infrastructure.yml` keeps the running image.
4. Run `frontend.yml` (manual dispatch or a push touching `frontend/`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AADSTS70021: No matching federated identity record` | The job is not running in the environment named in the federated credential (subject `repo:<owner>/<repo>:environment:<env>`), or the repository was renamed — re-run `setup-github-oidc`. |
| `AuthorizationFailed … roleAssignments/write` in Bicep | The identity lacks the condition-restricted RBAC Administrator role, or the template asks for a role outside the allowed list. |
| `unauthorized: authentication required` on `docker push` | AcrPush missing on the resource group, or `ACR_NAME` points at another environment's registry. |
| Deploy job waits forever | `prod` requires a reviewer: approve it under the run's *Review deployments*. |
