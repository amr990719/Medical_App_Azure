# Staging checklist

How to bring up **staging** the way dev was brought up (Sessions 11–12), in order. Commands and
reasons for each step: `docs/azure-deployment.md` (Bash) and `README.md` §9–§14 (PowerShell). The
dev walkthrough with every pitfall hit so far: `docs/deployment-path.md`.

Status (2026-10-11): **nothing for staging exists yet** except the empty GitHub environment
`staging`, which accepts protected branches only. Every step creates billable resources or
changes trust, so each needs the owner's go-ahead.

## 0. Decide first (blockers)

- [ ] **Region** (legal decision L3, `docs/final-report.md` §16 #1). Staging should match the
      intended prod region. The resource group's location is the region of every resource except
      the Static Web App.
- [x] **Admin MFA strategy** — decided 2026-10-11 (D150): Conditional Access only;
      `staging.bicepparam` has `entraAdminRequireMfa = false`. The CA policy (§4) must exist
      before the first staging admin is granted.
- [x] **OCR, malware scanning, private networking** — decided for production 2026-10-11 (D150):
      all off. Keep `ENABLE_OCR` and `ENABLE_PRIVATE_NETWORKING` unset on GitHub `staging` so
      staging matches prod.
- [ ] **Static Web App region**: the parameter defaults to `westeurope`, which refused new Static
      Web Apps in Session 11. Set `STATIC_WEB_APP_LOCATION` (dev uses `eastasia`).
- [ ] **Operator account**: a work account in the subscription's tenant avoids the security-default
      blocks (`AADSTS530035`) and the hourly re-sign-in that the personal guest account hits.
- [ ] **Cost**: staging keeps one replica warm (`minReplicas = 1`), uses PostgreSQL `Standard_B2s`
      and keeps 14-day backups (`docs/azure-deployment.md` §"Cost").

## 1. Resource group

```bash
SUB=<subscription-id>          # "Azure subscription 1", 247d882f-… (GitHub variable AZURE_SUBSCRIPTION_ID)
TENANT=<workforce-tenant-id>   # 448ad25b-… (GitHub variable AZURE_TENANT_ID)
az login --tenant "$TENANT"
az account set --subscription "$SUB"
RG=rg-medsyn-staging           # name is the owner's choice (dev uses Medical_App)
az group create -n "$RG" -l <region>
```

The eleven resource providers are already registered in this subscription (Session 11).

## 2. GitHub OIDC deploy identity

```bash
infrastructure/scripts/setup-github-oidc.sh --resource-group "$RG" --environment staging \
  --repo amr990719/Medical_App_Azure
```

(PowerShell: `setup-github-oidc.ps1 -ResourceGroup $RG -Environment staging -Repo …`.) It
checks that GitHub `staging` accepts protected branches only. It reads the repository's
immutable OIDC subject prefix and creates `id-medsyn-staging`, `id-github-medsyn-staging` and
the *Deployer (rg)* role with its assignments. It no longer creates a `-plan` identity. Git Bash
needs `MSYS_NO_PATHCONV=1`. Re-running the custom-role **update** path needs a Graph token
(Session 12).

- [ ] Set the GitHub `staging` variables the script prints: `AZURE_CLIENT_ID`,
      `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`. Also set
      `STATIC_WEB_APP_LOCATION`:

```bash
gh variable set STATIC_WEB_APP_LOCATION --env staging --repo amr990719/Medical_App_Azure --body eastasia
```

## 3. First phase (everything except the application)

```bash
export KEY_VAULT_OPERATOR_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)
export STATIC_WEB_APP_LOCATION=eastasia
unset CONTAINER_IMAGE                                   # phase 1: deployApplication=false
az deployment group what-if -g "$RG" -n main-staging \
  -f infrastructure/main.bicep -p infrastructure/parameters/staging.bicepparam
az deployment group create  -g "$RG" -n main-staging \
  -f infrastructure/main.bicep -p infrastructure/parameters/staging.bicepparam
```

- [ ] what-if shows creates only; deployment Succeeded. Note the outputs (Key Vault, ACR,
      PostgreSQL server, identity, Static Web App name and host, storage).

## 4. Entra app registration (staging)

In the External ID tenant (`medicalsyndicates.onmicrosoft.com`), with Arabic enabled on the user
flow first if it still isn't:

```bash
az login --tenant "$TENANT" --scope https://vault.azure.net/.default   # Key Vault token (Session 11)
az login --tenant 24135332-2a51-43e7-ae99-8b85467b7002 --allow-no-subscriptions
infrastructure/scripts/create-entra-app.sh --environment staging \
  --tenant-id 24135332-2a51-43e7-ae99-8b85467b7002 --public-url "https://$SWA_HOST" \
  --key-vault "$KV" --subscription "$SUB" --user-flow-id <signup-signin flow id>
```

- [ ] `medical-syndicates-staging` created (no `--local` for staging); `entra-client-secret` in
      the staging Key Vault.
- [ ] Set `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_AUTHORITY` on GitHub `staging`.
- [ ] Group `medical-admins-staging` and the Conditional Access MFA policy on the staging app
      (`docs/entra-setup.md` §4).

## 5. Key Vault secrets

```bash
umask 077; openssl rand -base64 48 > /tmp/dsk                          # never printed
az keyvault secret set --vault-name "$KV" --name django-secret-key --file /tmp/dsk --output none
shred -u /tmp/dsk 2>/dev/null || rm -f /tmp/dsk
```

- [ ] `django-secret-key` and `entra-client-secret` exist (`az keyvault secret list --vault-name "$KV" --query "[].name"`).

## 6. PostgreSQL (Entra admin, database, app role)

```bash
infrastructure/scripts/setup-postgres-entra.sh --resource-group "$RG" --server <psql-server> \
  --identity-name id-medsyn-staging --database medical --allow-current-ip
```

- [ ] Needs `psql` ≥ 15. The script removes its temporary firewall rule; check that it did
      (`az postgres flexible-server firewall-rule list`).

## 7. Second phase (image + application)

CI cannot do the first application deploy: `reusable-deploy-backend.yml` updates an existing
Container App and jobs. Build the image into the staging registry (`docker push` from this
machine timed out to uaenorth, D142):

```bash
# BuildKit task file acr-build.yaml from docs/deployment-path.md §11 (az acr build's legacy
# builder rejects RUN --mount); --no-logs avoids the Windows console 'charmap' crash
az acr run -r <staging-acr> -f acr-build.yaml --no-logs <context>/backend
export CONTAINER_IMAGE=<staging-acr>.azurecr.io/medical-backend:<git-sha>
export ENTRA_AUTHORITY=… ENTRA_TENANT_ID=… ENTRA_CLIENT_ID=…   # the staging values
az deployment group create -g "$RG" -n main-staging \
  -f infrastructure/main.bicep -p infrastructure/parameters/staging.bicepparam
```

Then start the migrate job and wait for `Succeeded` (`docs/azure-deployment.md` §7).

- [ ] Revision Healthy; `https://$SWA_HOST/api/ready/` → `{"status": "ok", "database": "ok"}`.
- [ ] `appInsightsDisableLocalAuth = true` in staging: check the app is configured for Entra
      ingestion (`APPLICATIONINSIGHTS_AUTHENTICATION=entra` and *Monitoring Metrics Publisher*,
      Q-T14). Otherwise telemetry is dropped silently.

## 8. Frontend and the remaining GitHub variables

- [ ] Deploy `frontend/dist` once with the SWA CLI (`docs/azure-deployment.md` §8), or let CI do
      it after step 10.
- [ ] Set on GitHub `staging`: `ACR_NAME`, `CONTAINER_APP_NAME`, `MIGRATE_JOB_NAME`,
      `CLEANUP_JOB_NAME`, `STATIC_WEB_APP_NAME` (deployment outputs). Optionally set
      `PUBLIC_HOSTNAME`, `ENABLE_OCR`, `ENABLE_PRIVATE_NETWORKING` and `POSTGRES_ENTRA_ADMIN_*`.
      Leave those unset to keep the defaults.

## 9. Smoke tests (through the Static Web App host only)

- [ ] `/` 200 with `<html lang="ar" dir="rtl">`; a deep link (`/doctor/form`) 200.
- [ ] `/api/health/` 200, `/api/ready/` `database: ok`; `/api/v1/auth/me/` → §46 401 envelope.
- [ ] `/api/v1/auth/login/` → 302 to `…ciamlogin.com/…/authorize` with the **staging** client id and
      redirect URI `https://$SWA_HOST/api/v1/auth/callback/`.
- [ ] Security headers present (CSP, HSTS, `X-Frame-Options: DENY`, nosniff).
- [ ] A doctor signs in, creates a draft, uploads an ID document and a receipt (private blob),
      sees the server fee quote, and submits (gets `MED-…`).
- [ ] `grant_admin` the test admin (one-off migrate-job execution,
      `docs/azure-deployment.md` §"One-off management commands"). The admin signs in with MFA,
      confirms the payment, requests a correction, the doctor resubmits, the admin approves.
      No print action is offered and `/application/{id}/print` / `/admin/applications/{id}/print`
      show the not-found page (application printing retired 2026-10-28).
- [ ] App Insights shows requests and traces with national IDs masked (`docs/azure-deployment.md`
      §"Telemetry verification").
- [ ] Restore drill A–C (`docs/azure-deployment.md` §"Restore drill"): staging is where it runs.

## 10. When to set `DEPLOY_STAGING=true`

Only after steps 1–9 pass, **and** once the owner accepts what it does to prod:

```bash
gh variable set DEPLOY_STAGING --repo amr990719/Medical_App_Azure --body true
```

From then on every merge to `main` deploys dev, then staging. It also **queues `deploy-prod`**
in all three workflows (`needs: deploy-staging`, no other condition). Those jobs wait for the
`prod` environment's required reviewer. Until prod exists (no variables on GitHub `prod`), the
reviewer must **reject** each prod deployment. An approved one fails at its first Azure step.
Turning staging off again: `gh variable delete DEPLOY_STAGING --repo amr990719/Medical_App_Azure`.
