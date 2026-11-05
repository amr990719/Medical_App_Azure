# GitHub setup (repository, environments, OIDC, variables)

How to connect this repository to GitHub Actions and Azure (PROMPT.md §36). Azure access uses
**GitHub OIDC federated credentials only**: no Azure password, service-principal secret or Static
Web Apps deployment token is stored in GitHub.

> **State (2026-11-05):** the repository and dev are set up and deploying through OIDC. The `prod`
> GitHub environment exists with a required reviewer and protected branches, but has no variables or
> Azure identity yet. Each change to GitHub settings needs the owner's explicit confirmation.
> Commands are given for the GitHub CLI (`gh` ≥ 2.40); every step can also be done in the web UI.
>
> **This repository is public**, so run logs, step summaries and workflow artifacts are public too.
> Workflows mask the subscription and tenant IDs, and nothing they upload holds a secret.

## Workflows

| File | Trigger | What it does |
|---|---|---|
| `.github/workflows/frontend.yml` | PR / push to `main` touching `frontend/**` | `npm ci` → lint → type check → Vitest → `rtl_check.py` → build; on `main`: store the build in the dev registry and deploy it to **dev only** (Static Web Apps) |
| `.github/workflows/backend.yml` | PR / push touching `backend/**` | ruff → lock check → `manage.py check` → migrations check → OpenAPI validation → pytest on a `postgres:16` service → build the runtime image once; on `main`: push to the dev ACR → **run the migrate job** → update the cleanup and notify jobs → new Container App revision → smoke test, **dev only** |
| `.github/workflows/infrastructure.yml` | PR / push touching `infrastructure/**`, manual | `bicep build` + lint of every file, `build-params`, script checks, release tooling tests; PR: no Azure access (D145); `main`: what-if + deploy **dev only**; manual (main only): dev or prod, optionally what-if only. A manual prod run is the way to change configuration between releases, and waits for the reviewer |
| `.github/workflows/e2e.yml` | PR to `main`, push to `main`, manual | fresh docker compose stack (PostgreSQL, Azurite, Django, dev auth, mock OCR) + Azurite pytest + Playwright (desktop and mobile). The run on `main` is what a production release requires |
| `.github/workflows/release-production.yml` | **manual only**, from `main` | the only way to production: `verify` → `export` → `preview` (first approval, what-if) → `deploy` (second approval). See `docs/production-runbook.md` |
| `.github/workflows/ci-gate.yml` | every PR to `main` (no path filter) | `release tooling`: actionlint, shellcheck, tooling tests, promotion test. `ci gate`: waits for whichever path-filtered workflows the change triggers |
| `.github/workflows/security-scan.yml` | weekly, PR touching locks or the Dockerfile, manual | `pip-audit`, `npm audit`, image scan, dependency review. No Azure access |
| `reusable-*.yml` | called by the above | deploy jobs for dev (frontend, backend) and for dev or a manual prod run (infrastructure) |

Every third-party action is pinned to a full commit SHA (tag in a comment). Workflow permissions
default to `contents: read`; only deploy jobs get `id-token: write`.

## 1. Create the repository (owner confirmation required)

```bash
gh repo create <owner>/<repo> --private --source . --remote origin   # creates the repo, no push
git push -u origin main                                              # first push — confirm first
```

## 2. Environments and protection rules

One GitHub environment per Azure environment:

| GitHub environment | Used by | Branch rule | Azure identity can |
|---|---|---|---|
| `dev` | merges to `main`, the export job of a release, manual runs | **protected branches only** (`main`) | deploy (custom *Deployer* role, AcrPush, condition-restricted RBAC admin) |
| `prod` | `release-production.yml`, manual infrastructure runs | **protected branches only** (`main`) and required reviewers | the same, in the production resource group |

The empty `staging` environment is left over and unused; deleting it is an owner step
(`docs/staging-checklist.md`).

On `pull_request` events the workflow files come from the PR branch, so anything a PR can reach
must be harmless: PR jobs get no Azure credential at all. The earlier `<env>-plan` environments
(read + what-if) were dropped: ARM what-if needs write permission on every resource in the template, so a read-only preview identity cannot work (D145). The deploy environments refuse
every ref except `main`, so an edited workflow on a branch (or a manual dispatch from a branch)
cannot get a deploy token.

```bash
gh api -X PUT "repos/<owner>/<repo>/environments/dev" --input - <<'JSON'
{"deployment_branch_policy": {"protected_branches": true, "custom_branch_policies": false}}
JSON
# prod: required reviewers, main only
gh api -X PUT "repos/<owner>/<repo>/environments/prod" --input - <<'JSON'
{
  "reviewers": [{"type": "User", "id": <user-id>}],
  "prevent_self_review": false,
  "deployment_branch_policy": {"protected_branches": true, "custom_branch_policies": false}
}
JSON
```

(`gh api users/<login> --jq .id` gives the user id.) With one maintainer, `prevent_self_review` stays
`false`, as it is today, or nobody could approve; a second reviewer can turn it on. "Protected
branches" relies on the branch protection of section 5.
`setup-github-oidc` reads these settings with `gh api` (read-only) and refuses to trust the deploy
identity while `<env>` accepts unprotected branches (or `prod` has no reviewers). Configure this
section first; `--skip-github-check` / `-SkipGitHubCheck` exists only for a repository that does
not exist yet and prints a warning.

## 3. Azure side: OIDC identities (once per environment)

Create the environment's resource group, then run the script (bash or PowerShell). It creates,
in that resource group only:

| Identity | Federated to | Roles (resource-group scope) |
|---|---|---|
| `id-medsyn-<env-short>` (the **app** identity, also declared by `main.bicep`) | — | none here; Bicep grants its data-plane roles |
| `id-github-medsyn-<env>` (deploy) | `<subject prefix>:environment:<env>`, where the prefix comes from `GET repos/<repo>/actions/oidc/customization/sub` (`repo:<owner>@<id>/<repo>@<id>` with immutable subjects) | custom **Deployer (&lt;rg&gt;)** = Contributor minus `federatedIdentityCredentials/write|delete` on managed identities (it cannot add a trust to the app identity and sign in as it) and minus storage `listKeys`, `regenerateKey`, `ListAccountSas`, `listServiceSas` (deploy Bicep, update the app and jobs, start the migrate job, read the SWA token); **AcrPush**; **Role Based Access Control Administrator** with an ABAC condition: create/delete only the six data-plane roles `main.bicep` grants (Blob Data Contributor, Blob Delegator, Key Vault Secrets User, AcrPull, OpenAI User, Monitoring Metrics Publisher) **and only for the app identity's principal id** — it cannot grant anything to itself or to any other identity |

The script no longer creates the retired `id-github-medsyn-<env>-plan` identity or the custom role *Deployment What-If Operator (&lt;rg&gt;)* (D145). dev's leftovers from an earlier run were deleted on 2026-10-11 (`docs/azure-deployment.md` §"Retired plan identity").

Residual risk, accepted and mitigated by the `main`-only environments and reviews: whoever can
deploy can run code as the app identity (deploying the app is exactly that), and the Deployer role
can still reconfigure resources (for example make a container public or switch Key Vault to
access policies). An
Azure Policy *deny* on `allowSharedKeyAccess`, public blob access and Key Vault access-policy mode
is the next hardening step (not written yet: it needs a subscription to test). Whether the custom what-if role covers every resource
type in the template is **NOT VERIFIED**: if what-if reports `AuthorizationFailed`, add the
missing read/validate action to that role, never a write action.

```bash
az login
az account set --subscription <subscription-id>
az group create --name rg-medsyn-dev --location <region> --tags application=medical-syndicates environment=dev
infrastructure/scripts/setup-github-oidc.sh --resource-group rg-medsyn-dev --environment dev --repo <owner>/<repo>
```

```powershell
./infrastructure/scripts/setup-github-oidc.ps1 -ResourceGroup rg-medsyn-dev -Environment dev -Repo <owner>/<repo>
```

For `prod`, the `github-oidc` stage of `bootstrap-production.sh` runs this script (separate resource
group, ideally a separate subscription, §49). Jobs that do not run in the matching GitHub environment
cannot obtain a token for it.

## 4. Environment variables

Settings → Environments → `<env>` → **Environment variables** (none of these is a secret). The only
GitHub secret is the environment secret `ALERT_EMAIL`, where alerts go: a secret so logs mask it, and
a production release refuses to run without it. For `prod`, the `github` stage of
`bootstrap-production.sh` sets these from the deployment outputs.
`KEY_VAULT_OPERATOR_*` is never set in GitHub: the deploy identity may not grant roles to people;
the operator's *Key Vault Secrets Officer* comes from the first-phase deployment run by a human
(`docs/azure-deployment.md` step 2) or from `az role assignment create`.

| Variable | Source | Used by |
|---|---|---|
| `AZURE_CLIENT_ID` | printed by `setup-github-oidc`: the **deploy** identity | every job that signs in (`azure/login`) |
| `AZURE_TENANT_ID` | printed by `setup-github-oidc` | all deploy jobs |
| `AZURE_SUBSCRIPTION_ID` | printed by `setup-github-oidc` | all deploy jobs |
| `AZURE_RESOURCE_GROUP` | your resource group | all deploy jobs |
| `ENTRA_AUTHORITY`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | printed by `create-entra-app` (`docs/entra-setup.md`) | infrastructure (Container App settings) |
| `ACR_NAME` | output `containerRegistryName` | backend, frontend (dev stores both artifacts there), release |
| `CONTAINER_APP_NAME` | output `containerAppName` | backend, release, infrastructure (keeps the running image) |
| `MIGRATE_JOB_NAME` | output `migrateJobName` | backend, release |
| `CLEANUP_JOB_NAME` | output `cleanupJobName` | backend, release |
| `NOTIFY_JOB_NAME` *(optional)* | output `notifyJobName`; set only where `enableNotifications` is on. When set, the deploy points the notify job at the new image; when unset, the step is skipped | backend, release |
| `STATIC_WEB_APP_NAME` | output `staticWebAppName` | frontend, release |
| `PUBLIC_HOSTNAME` *(optional)* | custom domain bound to the Static Web App | infrastructure |
| `STATIC_WEB_APP_LOCATION` *(optional)* | default `westeurope` | infrastructure |
| `ENABLE_OCR` *(optional)* | dev only; production pins OCR off (D150) | infrastructure |
| `ENABLE_PRIVATE_NETWORKING` *(optional)* | ignored in prod: `prod.bicepparam` pins `false` (D150); `ENABLE_OCR` likewise | infrastructure |
| `POSTGRES_ENTRA_ADMIN_OBJECT_ID` / `_NAME` / `_TYPE` *(optional)* | Entra admin group of the PostgreSQL server | infrastructure |
| `ENABLE_NOTIFICATIONS`, `NOTIFICATIONS_MODE`, `SES_ACCESS_KEY_FROM_KEY_VAULT`, `SES_REGION`, `SES_FROM_ADDRESS` *(optional)* | `docs/production-runbook.md`, "Notifications"; unset means off | infrastructure, release |
| `RECOVERY_HOLD`, `POSTGRES_SERVER_NAME_OVERRIDE` *(recovery only)* | set by `recovery.sh`; the parameter files read them, so every later deployment keeps them, and a release refuses to run during a hold | infrastructure, release |

```bash
gh variable set AZURE_CLIENT_ID --env dev --repo <owner>/<repo> --body <client-id>
# … one line per variable; after the first infrastructure deployment:
az deployment group show -g rg-medsyn-dev -n main-dev --query properties.outputs -o json
```

## 5. Branch protection for `main`

Today (read from the API on 2026-11-05) `main` requires a pull request with 0 approvals (the
single-maintainer setting, D143), dismisses stale reviews, requires resolved conversations, enforces
all of it for admins, and blocks force pushes and deletion. **No status check is required.** The
command below keeps those settings and adds the two checks that run on every PR. It has **not** been
run; it needs the owner's confirmation:

```bash
gh api -X PUT "repos/<owner>/<repo>/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": {"strict": false, "contexts": ["ci gate", "release tooling"]},
  "enforce_admins": true,
  "required_pull_request_reviews": {"required_approving_review_count": 0, "dismiss_stale_reviews": true},
  "restrictions": null,
  "required_conversation_resolution": true,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Status checks only appear in the list after they ran once, so run this after the first PR that
carries `ci-gate.yml`. **Never require a path-filtered check**, such as `playwright` or `build image`:
it would block every PR that does not trigger it, forever. Do not make `ci gate` depend on another
job either, because a job skipped by a failed `needs` reports success to branch protection. Also
enable: Settings → Actions → General → *Workflow permissions: Read repository contents*; Settings →
Code security → secret scanning and push protection.

## 6. First deployment order

**Production:** follow "Bootstrap" in `docs/production-runbook.md`. `bootstrap-production.sh` does the
foundation, then `release-production.yml` in `bootstrap` mode applies the schema before anything
serves. There is no manual image push.

**Dev, if it ever had to be rebuilt:**

1. `infrastructure.yml` runs on the first push (or manually): with no Container App yet it deploys
   the **first phase** (everything except the app, its jobs and the SWA link).
2. Set the Key Vault secrets, create the Entra app, run `setup-postgres-entra.sh`
   (`docs/azure-deployment.md`, steps 4–6). Fill the variables of section 4.
3. Create the application once by hand (second phase, `docs/azure-deployment.md` step 7: push
   the first image, deploy with `CONTAINER_IMAGE` set). `backend.yml` updates an existing
   Container App, so it cannot do this first creation; from then on every push to `main`
   deploys to dev, and `infrastructure.yml` keeps the running image.
4. Run `frontend.yml` (manual dispatch or a push touching `frontend/`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AADSTS70021: No matching federated identity record` | The job is not running in the environment named in the federated credential (subject `repo:<owner>/<repo>:environment:<env>`), or the repository was renamed — re-run `setup-github-oidc`. |
| `AuthorizationFailed … roleAssignments/write` in Bicep | The identity lacks the condition-restricted RBAC Administrator role, the template asks for a role outside the allowed list, the target principal is not the app identity (re-run `setup-github-oidc` if the app identity was recreated), or `KEY_VAULT_OPERATOR_*` was set in GitHub. |
| `setup-github-oidc` stops with "must allow protected branches only" | Configure section 2 (and branch protection, section 5) first. |
| `AuthorizationFailed` on `federatedIdentityCredentials` or `listKeys` in a workflow | Intended: the Deployer role excludes them. Do those operations as an operator. |
| `AADSTS70021` on a branch run or manual dispatch | Expected: `<env>` accepts `main` only. Dispatch from `main`; preview a branch by merging it, or run `az deployment group what-if` locally. |
| `unauthorized: authentication required` on `docker push` | AcrPush missing on the resource group, or `ACR_NAME` points at another environment's registry. |
| Deploy job waits forever | `prod` requires a reviewer: approve it under the run's *Review deployments*. A release asks twice: once for the preview, once for the deployment. |
| Release refused: no run on main for a commit | The commit predates the push-triggered e2e, or that workflow failed. Merge a new commit that changes the component, or pick another commit (`infrastructure/scripts/release_gate.py`). |
