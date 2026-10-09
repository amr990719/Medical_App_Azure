# Deployment Path: Azure and GitHub

This guide is the end-to-end path for taking the app from local code to a deployed Azure
environment with GitHub Actions. Start with `dev`, prove the full flow, then repeat for
`staging` and `prod`.

The app deploys as:

- React/Vite frontend -> Azure Static Web Apps
- Django backend -> Azure Container Apps
- PostgreSQL -> Azure Database for PostgreSQL Flexible Server
- uploaded documents -> Azure Blob Storage
- secrets -> Azure Key Vault
- CI/CD -> GitHub Actions with Azure OIDC, not stored Azure passwords
- production sign-in -> Microsoft Entra External ID

## 1. Deployment Map

```text
Local machine
  |
  | 1. Verify the app locally
  v
Git repository
  |
  | 2. Create GitHub repo and push main
  v
GitHub platform setup
  |
  | 3. Create environments: dev, dev-plan, staging, staging-plan, prod, prod-plan
  | 4. Protect main and configure prod reviewers
  v
Azure platform setup
  |
  | 5. Create Azure resource group
  | 6. Create GitHub OIDC identities for the environment
  v
Azure infrastructure phase 1
  |
  | 7. Deploy Bicep without CONTAINER_IMAGE
  |    Creates foundation resources, not the Container App yet
  v
Identity and secrets
  |
  | 8. Put django-secret-key in Key Vault
  | 9. Create Entra External ID app registration
  | 10. Configure PostgreSQL Entra admin and managed-identity database role
  v
Application phase 2
  |
  | 11. Build backend Docker image
  | 12. Push image to Azure Container Registry
  | 13. Redeploy Bicep with CONTAINER_IMAGE
  |     Creates Container App, migrate job, cleanup job, and Static Web App backend link
  | 14. Run migration job once
  v
Frontend deployment
  |
  | 15. Build frontend
  | 16. Deploy frontend/dist to Static Web Apps
  v
First production-style check
  |
  | 17. Open the Static Web App URL
  | 18. Sign in with Entra External ID
  | 19. Grant the first admin role
  | 20. Test doctor flow, admin flow, uploads, print, health checks
  v
Ongoing delivery
  |
  | 21. Add GitHub environment variables
  | 22. Push to main
  | 23. GitHub Actions deploy infrastructure, backend, and frontend
  v
Staging and production
  |
  | 24. Repeat the same path for staging
  | 25. Repeat for prod with reviewers, backups, private-networking decision, and legal approvals
```

## 2. Decisions Before Deployment

| Decision | Recommended starting point |
|---|---|
| First environment | `dev` |
| Azure region | Use the approved data-residency region. Static Web Apps must use a supported SWA region such as `westeurope`, `centralus`, `eastus2`, `westus2`, or `eastasia`. |
| Git branch | `main` |
| GitHub repo visibility | Private |
| Production private networking | Decide before the first `prod` deployment. PostgreSQL networking cannot be changed later without rebuilding. |
| OCR | Keep off until legal/privacy approval. Enable later with `ENABLE_OCR=true`. |
| Entra External ID | Required for deployed sign-in. Local dev sign-in is not used in Azure production settings. |

## 3. Local Preflight

Run the app locally first:

```powershell
cd C:\Users\admin\Desktop\Medical_App_Azure
npm run up
npm run dev
```

Open:

```text
http://localhost:5173
```

Check the backend:

```powershell
curl.exe http://localhost:8000/api/ready/
```

Expected:

```json
{"status":"ok","database":"ok"}
```

Run the checks before the first cloud deployment:

```powershell
npm run lint
npm test
```

If you need a smaller check, run:

```powershell
npm run test:backend
npm run test:frontend
```

## 4. GitHub Setup

### 4.1 Create The Repository

Install and authenticate GitHub CLI:

```powershell
gh auth login
```

Create the private repository and push:

```powershell
cd C:\Users\admin\Desktop\Medical_App_Azure
git status
gh repo create <owner>/<repo> --private --source . --remote origin
git push -u origin main
```

Replace `<owner>/<repo>` with your GitHub owner and repository name.

### 4.2 Create GitHub Environments

Create these environments:

```text
dev
dev-plan
staging
staging-plan
prod
prod-plan
```

In GitHub UI:

```text
Repository -> Settings -> Environments -> New environment
```

| Environment | Purpose |
|---|---|
| `dev`, `staging`, `prod` | Real deployments |
| `dev-plan`, `staging-plan`, `prod-plan` | Read-only what-if / preview identities |

For `prod`, require reviewers. For deploy environments, restrict deployment branches to protected
branches after branch protection is configured.

### 4.3 Protect `main`

In GitHub UI:

```text
Repository -> Settings -> Branches -> Add branch protection rule
```

Recommended settings:

- require pull request before merging
- require at least one approval
- require status checks after the first workflow run has created them
- require branches to be up to date before merging
- block force pushes
- block branch deletion

With a single maintainer, use 0 required approvals (one approval would block every merge), and
enforce the rule for admins. Every workflow is path-filtered, so a required check whose workflow
did not run blocks the PR forever: require only checks that run on every PR (or add a gate job).

Workflow check names come from:

```text
.github/workflows/frontend.yml
.github/workflows/backend.yml
.github/workflows/infrastructure.yml
.github/workflows/e2e.yml
```

### 4.4 GitHub Actions Permissions

In GitHub UI:

```text
Repository -> Settings -> Actions -> General
```

Set workflow permissions to read repository contents. Deploy jobs request `id-token: write` only
where Azure OIDC is needed.

## 5. Azure Setup

### 5.1 Install Tools

Required locally:

- Azure CLI
- Azure Bicep CLI through Azure CLI
- Docker Desktop
- Node.js 22
- GitHub CLI
- PowerShell
- `psql` 15 or newer for PostgreSQL setup

Check:

```powershell
az version
az bicep version
docker --version
node --version
npm --version
gh --version
psql --version
```

If Bicep is missing:

```powershell
az bicep install
```

### 5.2 Register Azure Providers

Run once per subscription:

```powershell
$providers = @(
  "Microsoft.App",
  "Microsoft.ContainerRegistry",
  "Microsoft.DBforPostgreSQL",
  "Microsoft.KeyVault",
  "Microsoft.Storage",
  "Microsoft.Web",
  "Microsoft.OperationalInsights",
  "Microsoft.Insights",
  "Microsoft.ManagedIdentity",
  "Microsoft.CognitiveServices",
  "Microsoft.Network"
)

foreach ($provider in $providers) {
  az provider register --namespace $provider
}
```

### 5.3 Create The Dev Resource Group

```powershell
az login
az account set --subscription <subscription-id>

$EnvName = "dev"
$RG = "rg-medsyn-dev"
$Location = "<azure-region>"

az group create `
  --name $RG `
  --location $Location `
  --tags application=medical-syndicates environment=$EnvName
```

Use the region approved by the organization.

## 6. Connect GitHub To Azure With OIDC

Run this once per environment. Start with `dev`.

```powershell
.\infrastructure\scripts\setup-github-oidc.ps1 `
  -ResourceGroup rg-medsyn-dev `
  -Environment dev `
  -Repo <owner>/<repo>
```

This creates:

| Azure identity | GitHub environment | Capability |
|---|---|---|
| `id-github-medsyn-dev` | `dev` | Deploy infrastructure and app |
| `id-github-medsyn-dev-plan` | `dev-plan` | Read-only what-if |
| `id-medsyn-dev` | none | Runtime identity used by the app |

Save the printed values for GitHub environment variables:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP
```

Repeat later for `staging` and `prod`.

## 7. Azure Infrastructure Phase 1

Phase 1 creates the foundation resources but not the app container yet.

It creates:

- managed identity
- Log Analytics
- Application Insights
- Key Vault
- Storage account and private Blob container
- PostgreSQL Flexible Server
- Container Registry
- Container Apps environment
- Static Web App
- runtime role assignments

It does not create yet:

- Django Container App
- migration job
- cleanup job
- Static Web App linked backend

Reason: Container Apps resolve Key Vault references at creation time, so required secrets must exist
before the app is created.

Run:

```powershell
$EnvName = "dev"
$RG = "rg-medsyn-dev"

$env:KEY_VAULT_OPERATOR_OBJECT_ID = az ad signed-in-user show --query id -o tsv
$env:KEY_VAULT_OPERATOR_TYPE = "User"
Remove-Item Env:CONTAINER_IMAGE -ErrorAction SilentlyContinue

az deployment group what-if `
  -g $RG `
  -n "main-$EnvName" `
  -f infrastructure/main.bicep `
  -p "infrastructure/parameters/$EnvName.bicepparam"

az deployment group create `
  -g $RG `
  -n "main-$EnvName" `
  -f infrastructure/main.bicep `
  -p "infrastructure/parameters/$EnvName.bicepparam"
```

Capture outputs:

```powershell
function Get-Out($Name) {
  az deployment group show `
    -g $RG `
    -n "main-$EnvName" `
    --query "properties.outputs.$Name.value" `
    -o tsv
}

$KV = Get-Out keyVaultName
$ACR = Get-Out containerRegistryName
$PG = Get-Out postgresServerName
$IDENTITY = Get-Out identityName
$SWA_HOST = Get-Out staticWebAppHostname
$SWA_NAME = Get-Out staticWebAppName

Write-Host "Key Vault: $KV"
Write-Host "ACR: $ACR"
Write-Host "Postgres: $PG"
Write-Host "Runtime identity: $IDENTITY"
Write-Host "Static Web App host: $SWA_HOST"
```

## 8. Key Vault Secrets

Create the Django secret key:

```powershell
$tmp = New-TemporaryFile
python -c "import secrets,sys; open(sys.argv[1],'w').write(secrets.token_urlsafe(64))" $tmp.FullName

az keyvault secret set `
  --vault-name $KV `
  --name django-secret-key `
  --file $tmp.FullName `
  --output none

Remove-Item $tmp.FullName
```

The Entra client secret is created by the Entra app script and stored in Key Vault as:

```text
entra-client-secret
```

## 9. Entra External ID Setup

In Azure, create or use an Entra External ID tenant for real sign-in.

At a high level:

1. Create the External ID tenant.
2. Create a sign-up/sign-in user flow.
3. Enable Arabic/localized branding as needed.
4. Create one app registration per environment.
5. Configure redirect URI: `https://<static-web-app-host>/api/v1/auth/callback/`.
6. Configure post-logout redirect URI: `https://<static-web-app-host>/signed-out`.

Use the repo script:

```powershell
az login --tenant <workforce-tenant-id>
az login --tenant <external-tenant-id> --allow-no-subscriptions

.\infrastructure\scripts\create-entra-app.ps1 `
  -Environment dev `
  -TenantId <external-tenant-id> `
  -PublicUrl "https://$SWA_HOST" `
  -KeyVault $KV `
  -Subscription <subscription-id> `
  -UserFlowId <user-flow-id>
```

Save the printed values:

```text
ENTRA_AUTHORITY
ENTRA_TENANT_ID
ENTRA_CLIENT_ID
```

Set them in the current shell for phase 2:

```powershell
$env:ENTRA_AUTHORITY = "https://<tenant-subdomain>.ciamlogin.com/<external-tenant-id>"
$env:ENTRA_TENANT_ID = "<external-tenant-id>"
$env:ENTRA_CLIENT_ID = "<application-client-id>"
```

## 10. PostgreSQL Entra Setup

The app uses managed identity to connect to PostgreSQL. Run the database setup script after the
server exists.

In Git Bash or WSL:

```bash
infrastructure/scripts/setup-postgres-entra.sh \
  --resource-group rg-medsyn-dev \
  --server "$PG" \
  --identity-name "$IDENTITY" \
  --database medical \
  --allow-current-ip
```

This:

- sets an Entra administrator for PostgreSQL
- creates the `medical` database
- creates the managed identity database principal
- grants the identity database permissions

For private-networked production, run this from inside the VNet and do not use `--allow-current-ip`.

## 11. Application Phase 2: Backend Image And Container App

Build the backend runtime image:

```powershell
$LoginServer = az acr show -n $ACR --query loginServer -o tsv
$Tag = git rev-parse HEAD

docker build --target runtime -t "$LoginServer/medical-backend:$Tag" backend/
```

Push it:

```powershell
az acr login -n $ACR
docker push "$LoginServer/medical-backend:$Tag"
```

Redeploy Bicep with the image:

```powershell
$env:CONTAINER_IMAGE = "$LoginServer/medical-backend:$Tag"

az deployment group create `
  -g $RG `
  -n "main-$EnvName" `
  -f infrastructure/main.bicep `
  -p "infrastructure/parameters/$EnvName.bicepparam"
```

This creates the Container App, migrate job, cleanup job, and Static Web App linked backend.

Run the migration job:

```powershell
$APP = Get-Out containerAppName
$MIGRATE = Get-Out migrateJobName

$Exec = az containerapp job start `
  -n $MIGRATE `
  -g $RG `
  --query name `
  -o tsv

do {
  Start-Sleep -Seconds 10
  $Status = az containerapp job execution show `
    -n $MIGRATE `
    -g $RG `
    --job-execution-name $Exec `
    --query properties.status `
    -o tsv
  Write-Host "Migration status: $Status"
} while ($Status -notin "Succeeded","Failed")

if ($Status -ne "Succeeded") {
  throw "Migration job failed"
}
```

Check backend readiness through the Static Web App. Linking the Static Web App enables
`azureStaticWebApps` authentication on the Container App, so its own FQDN answers **401** to
everything; that is expected. `/api` on the Static Web App host only works once a frontend build
has been deployed (§12), so run this after §12:

```powershell
curl.exe -fsS "https://$SWA_HOST/api/ready/"   # {"status": "ok", "database": "ok"}
```

To see a revision that never becomes ready, read the platform events and the console:

```powershell
az containerapp revision list -n $APP -g $RG -o table
az containerapp logs show -n $APP -g $RG --type system --format json --tail 30
az containerapp logs show -n $APP -g $RG --type console --tail 40
```

If `docker push` from your machine stalls on large layers, or `az acr login` fails with
`AADSTS530035` (security defaults refusing the token for a personal Microsoft account), build
the image in the registry instead. ACR quick builds (`az acr build`) use the legacy builder and
reject the Dockerfile's `RUN --mount`, so use a task file with BuildKit, placed in a clean
`git archive` of `backend/` (the task file must sit inside the uploaded build context):

```powershell
$Ctx = Join-Path $env:TEMP "acr-ctx"
Remove-Item -Recurse -Force $Ctx -ErrorAction SilentlyContinue
New-Item -ItemType Directory $Ctx | Out-Null
git archive -o "$Ctx\backend.tar" HEAD backend
tar -xf "$Ctx\backend.tar" -C $Ctx
@"
version: v1.1.0
steps:
  - build: --target runtime -t `$Registry/medical-backend:$Tag -f Dockerfile .
    env: ["DOCKER_BUILDKIT=1"]
  - push: ["`$Registry/medical-backend:$Tag"]
"@ | Set-Content -Encoding ascii "$Ctx\backend\acr-build.yaml"
az acr run -r $ACR -f acr-build.yaml --no-logs "$Ctx\backend"
az acr task list-runs -r $ACR --top 1 --query "[0].{run:runId,status:status,tag:outputImages[0].tag}" -o table
```

Use `--no-logs`: streaming the build log crashes the CLI on a Windows console (`'charmap' codec`).

## 12. Frontend Deployment

Build:

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

Deploy to Static Web Apps:

```powershell
$Token = az staticwebapp secrets list `
  -n $SWA_NAME `
  -g $RG `
  --query properties.apiKey `
  -o tsv

npx --yes @azure/static-web-apps-cli@2 deploy frontend/dist `
  --deployment-token $Token `
  --env production

Remove-Variable Token
```

Open:

```text
https://<static-web-app-host>/
```

Use the Static Web App host, not the Container App host. The frontend calls `/api`, and Static Web
Apps forwards `/api` to the linked Container App so cookies stay same-origin.

## 13. Grant The First Admin

The first admin must sign in once so the user exists in the database. Then grant admin:

```powershell
az containerapp exec `
  -n $APP `
  -g $RG `
  --command "python manage.py grant_admin <email-or-entra-oid>"
```

Then add the same user to the Entra admin group used by the admin MFA policy.

## 14. GitHub Environment Variables

After the first Azure deployment, fill GitHub variables for each environment.

In GitHub:

```text
Repository -> Settings -> Environments -> dev -> Environment variables
```

Set:

| Variable | Value source |
|---|---|
| `AZURE_CLIENT_ID` | printed by `setup-github-oidc.ps1` for the deploy identity |
| `AZURE_TENANT_ID` | printed by `setup-github-oidc.ps1` |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription id |
| `AZURE_RESOURCE_GROUP` | `rg-medsyn-dev` |
| `ENTRA_AUTHORITY` | printed by `create-entra-app.ps1` |
| `ENTRA_TENANT_ID` | printed by `create-entra-app.ps1` |
| `ENTRA_CLIENT_ID` | printed by `create-entra-app.ps1` |
| `ACR_NAME` | Bicep output `containerRegistryName` |
| `CONTAINER_APP_NAME` | Bicep output `containerAppName` |
| `MIGRATE_JOB_NAME` | Bicep output `migrateJobName` |
| `CLEANUP_JOB_NAME` | Bicep output `cleanupJobName` |
| `STATIC_WEB_APP_NAME` | Bicep output `staticWebAppName` |
| `PUBLIC_HOSTNAME` | Optional custom domain |
| `STATIC_WEB_APP_LOCATION` | Optional, default is `westeurope` |
| `ENABLE_OCR` | Optional, `true` only after approval |
| `ENABLE_PRIVATE_NETWORKING` | Optional. Decide before first prod deployment. |
| `POSTGRES_ENTRA_ADMIN_OBJECT_ID` | Optional group/user object id |
| `POSTGRES_ENTRA_ADMIN_NAME` | Optional group/user display name |
| `POSTGRES_ENTRA_ADMIN_TYPE` | Optional `Group` or `User` |

For `dev-plan`, set the same Azure variables, but use the plan identity client id for
`AZURE_CLIENT_ID`.

Repeat for `staging`, `staging-plan`, `prod`, and `prod-plan` when those environments are ready.

## 15. How GitHub Actions Deploys After Setup

Once the first deployment exists, normal delivery is:

```text
push to main
  |
  |-- infrastructure.yml
  |     validates Bicep
  |     runs what-if
  |     deploys infrastructure dev -> staging -> prod
  |
  |-- backend.yml
  |     runs ruff, Django checks, migration check, pytest
  |     builds runtime image
  |     pushes image to each ACR
  |     updates migrate job image
  |     runs migrate job once
  |     updates cleanup job image
  |     updates Container App revision
  |     smoke-tests /api/ready/
  |
  |-- frontend.yml
  |     runs lint, typecheck, tests, RTL check, build
  |     deploys frontend/dist to Static Web Apps
  |
  |-- e2e.yml
        runs local docker compose and Playwright on pull requests/manual runs
```

Important: `backend.yml` expects the Container App and jobs to already exist. That is why the first
backend creation is manual in phase 2.

## 16. Validation Checklist

After deployment, verify:

- Static Web App opens at `https://<SWA_HOST>/`
- `/api` calls happen on the same host as the frontend
- `https://<SWA_HOST>/api/ready/` returns database ok
- Entra sign-in works
- first admin can access `/admin`
- doctor can create/fill an application
- document upload works
- payment receipt upload works
- admin can confirm payment
- admin can approve/request correction/reject
- print page opens and prints A4
- logs appear in Application Insights / Log Analytics
- migration job reports `Succeeded`
- cleanup job exists with the expected cron

## 17. Repeat For Staging

Repeat the same sequence with:

```text
ENV = staging
RG = rg-medsyn-staging
parameter file = infrastructure/parameters/staging.bicepparam
GitHub environments = staging and staging-plan
```

Use a separate Entra app registration for staging.

Pushes to `main` deploy to staging (and then to prod, after approval) only once staging is
enabled. When the staging environment and its variables are complete, set the repository
variable:

```powershell
gh variable set DEPLOY_STAGING --body true
```

Until then the `deploy-staging` jobs, and so `deploy-prod`, are skipped.

## 18. Repeat For Production

Before production:

- confirm legal/data-region decision
- confirm OCR decision
- decide private networking before first prod deployment
- configure prod GitHub reviewers
- confirm backup retention in `prod.bicepparam`
- run a restore drill in staging
- confirm monitoring and alerting expectations
- confirm custom domain, if any
- create production Entra app registration
- configure admin MFA group

Then repeat with:

```text
ENV = prod
RG = rg-medsyn-prod
parameter file = infrastructure/parameters/prod.bicepparam
GitHub environments = prod and prod-plan
```

Production should deploy from protected `main` only and require reviewer approval.

## 19. Common Problems

| Symptom | Likely fix |
|---|---|
| `AUTH_UNAVAILABLE` in Azure | Entra variables or `entra-client-secret` are missing. Re-check `ENTRA_AUTHORITY`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, and Key Vault secret. |
| Login redirect mismatch | Re-run `create-entra-app.ps1` with the exact public URL. Redirect URI must end with `/api/v1/auth/callback/`. |
| API calls return 401 after login | Use the Static Web App URL, not the Container App URL. The app depends on same-origin `/api`. |
| CSRF 403 | Public hostname is missing from `CSRF_TRUSTED_ORIGINS`; set `PUBLIC_HOSTNAME` and redeploy. |
| Container App revision never ready | Production settings are missing a required secret or variable. Check Container App logs. |
| Startup probe fails with 400, console shows `DisallowedHost: 'localhost:8000'` | Something validates the Host header before `HealthProbeMiddleware`. It must stay `MIDDLEWARE[0]`; `configure_telemetry()` places the OTel Django middleware at position 1. |
| Admin completes MFA but sees "حسابات المسؤولين تتطلب التحقق بخطوتين" (`MFA_REQUIRED`) | External ID v2.0 ID tokens carry no `amr`, so the app cannot see MFA. Enforce admin MFA with Conditional Access and set `entraAdminRequireMfa = false` (D144). |
| Container App FQDN returns 401 for every path | Expected after the Static Web App link: only the Static Web App may call it. Test through `https://<static-web-app-host>/api/...`. |
| `/api/...` on the Static Web App returns its HTML 404 page | No frontend build deployed yet, or the linked backend is missing (`az staticwebapp backends show`). |
| `az acr login` fails with `AADSTS530035`, or `docker push` stalls on a layer | Build in the registry with `az acr run` and a BuildKit task file (§11). |
| PostgreSQL auth fails | `setup-postgres-entra.sh` was not run, or the app identity/client id points to the wrong tenant. |
| Blob upload fails | Role assignments may still be propagating, or Blob account URL/container settings are wrong. |
| GitHub OIDC fails with `AADSTS70021` | GitHub job environment does not match the federated credential subject, or repo name changed. Re-run `setup-github-oidc.ps1`. |
| `azure/login` fails with `AADSTS700213` for subject `repo:<owner>@<id>/<repo>@<id>:environment:<env>` | The repository uses immutable OIDC subjects. `setup-github-oidc` now reads the prefix from `GET repos/<repo>/actions/oidc/customization/sub`; re-run it (or update the federated credential subject). |
| Docker push unauthorized | The GitHub deploy identity needs AcrPush, or `ACR_NAME` points to the wrong registry. |

## 20. Source Files To Know

| File | Purpose |
|---|---|
| `infrastructure/main.bicep` | Main Azure infrastructure template |
| `infrastructure/parameters/dev.bicepparam` | Dev sizing and environment-variable inputs |
| `infrastructure/parameters/staging.bicepparam` | Staging sizing |
| `infrastructure/parameters/prod.bicepparam` | Production sizing |
| `infrastructure/scripts/setup-github-oidc.ps1` | Creates Azure identities/federated credentials for GitHub |
| `infrastructure/scripts/create-entra-app.ps1` | Creates Entra app registration and stores client secret |
| `infrastructure/scripts/setup-postgres-entra.sh` | Configures PostgreSQL Entra auth/database role |
| `.github/workflows/infrastructure.yml` | Bicep validation and deployment |
| `.github/workflows/backend.yml` | Backend test/image/deploy pipeline |
| `.github/workflows/frontend.yml` | Frontend test/build/deploy pipeline |
| `.github/workflows/e2e.yml` | Docker Compose + Playwright checks |
| `docs/azure-deployment.md` | Detailed Azure operations and recovery notes |
| `docs/github-setup.md` | Detailed GitHub environments/OIDC setup |
| `docs/entra-setup.md` | Detailed Entra External ID setup |
