# Azure deployment

Exact commands to create one environment (`dev`, `staging` or `prod`) and deploy the platform to
it (PROMPT.md §33–§37, §48, §52). Architecture: `docs/architecture.md`. CI/CD: `docs/github-setup.md`.
Sign-in: `docs/entra-setup.md`.

Commands are Bash (Git Bash or WSL on Windows). The same steps in Windows PowerShell are in
`README.md` §9–§14.

> **NOT VERIFIED — requires Azure credentials.** No Azure resource was created while writing
> this. Every Bicep file builds and lints with zero warnings (`az bicep build`, `az bicep lint`,
> strict `infrastructure/bicepconfig.json`) and the parameter files compile; `az deployment group
> what-if` could not run because the only available subscription is disabled (read-only).

## What gets deployed (per environment, one resource group)

| Module | Resource | Notes |
|---|---|---|
| `identity.bicep` | user-assigned identity `id-medsyn-<env>` | used by the app and both jobs for Blob, Key Vault, PostgreSQL, ACR, OpenAI, App Insights |
| `monitoring.bicep` | Log Analytics + Application Insights | retention / daily cap / Entra-only ingestion parameters |
| `key-vault.bicep` | Key Vault (RBAC, soft delete, purge protection) | secrets set by you, never by Bicep |
| `storage.bicep` | Storage account + private container `medical-documents` | no public access, **shared keys disabled**, TLS 1.2, soft delete, versioning, lifecycle for old versions |
| `postgres.bicep` | PostgreSQL Flexible Server 16 | Entra auth on, password auth off by default, TLS ≥ 1.2 required, PITR + optional geo backup / HA |
| `container-registry.bicep` | Container Registry | no admin user, no anonymous pull |
| `container-apps-env.bicep` | Container Apps environment (workload profiles, Consumption) | logs to Log Analytics |
| `container-app.bicep` | Django app + `migrate` job (manual) + `cleanup` job (cron) | Key Vault references, probes on `/api/health/` + `/api/ready/`, HTTP-concurrency scaling |
| `static-web-app.bicep` | Static Web App **Standard** | PR preview environments disabled (they would share the backend) |
| `static-web-app-link.bicep` | linked backend → Container App | `/api/*` same origin (§4.1) |
| `role-assignments.bicep` | Blob Data Contributor (container), Blob Delegator (account), Key Vault Secrets User, AcrPull, Monitoring Metrics Publisher, OpenAI User | each scoped to one resource |
| `openai.bicep` | Azure OpenAI + vision deployment | only with `enableOcr=true`; keys disabled |
| `network.bicep`, `private-endpoints.bicep` | VNet, delegated subnets, private DNS, private endpoints | only with `enablePrivateNetworking=true` |

Names are `<type>-medsyn-<env>-<uniqueString(resource group, env)>` (no hard-coded global names);
everything carries the tags `application`, `environment`, `managed-by`.

## 0. Prerequisites

- Azure CLI ≥ 2.60 (`az bicep install`), `psql` ≥ 15 for step 6, bash (Git Bash/WSL on Windows)
  or PowerShell for the scripts.
- Rights on the target subscription: Owner, or Contributor + User Access Administrator, on the
  resource group (role assignments are part of the template).
- **Region.** Decide with legal (decision L3). All resources except the Static Web App use the
  resource group's region; Static Web Apps exists only in `westeurope`, `centralus`, `eastus2`,
  `westus2`, `eastasia` (`STATIC_WEB_APP_LOCATION`). Check subscription policies first:

  ```bash
  az policy assignment list --disable-scope-strict-match \
    --query "[].{name:displayName, params:parameters}" -o json
  ```

  (The subscription used during development allows only `switzerlandnorth`,
  `germanywestcentral`, `francecentral`, `polandcentral`, `italynorth` — none of them offers Static
  Web Apps; see Q-T15 in `docs/progress.md`.)
- Register the resource providers once per subscription:

  ```bash
  for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL Microsoft.KeyVault \
            Microsoft.Storage Microsoft.Web Microsoft.OperationalInsights Microsoft.Insights \
            Microsoft.ManagedIdentity Microsoft.CognitiveServices Microsoft.Network; do
    az provider register --namespace "$ns"
  done
  ```

## 1. Sign in and create the resource group

```bash
az login
az account set --subscription <subscription-id>
ENV=dev                                   # dev | staging | prod
RG=rg-medsyn-$ENV
LOCATION=<region>
az group create --name "$RG" --location "$LOCATION" \
  --tags application=medical-syndicates environment=$ENV
```

## 2. Choose the per-environment values (shell variables, never committed)

The parameter files (`infrastructure/parameters/<env>.bicepparam`) contain sizes only; tenant- and
principal-specific values are read from environment variables:

```bash
export KEY_VAULT_OPERATOR_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv)"   # who sets secrets
export KEY_VAULT_OPERATOR_TYPE=User
# Optional: Entra admin group of PostgreSQL (otherwise step 6 sets you as admin)
# export POSTGRES_ENTRA_ADMIN_OBJECT_ID=<group-object-id> POSTGRES_ENTRA_ADMIN_NAME=<group-name> POSTGRES_ENTRA_ADMIN_TYPE=Group
# export STATIC_WEB_APP_LOCATION=westeurope
# prod only, decide now (PostgreSQL networking cannot be changed later):
# export ENABLE_PRIVATE_NETWORKING=false
unset CONTAINER_IMAGE   # first phase
```

## 3. First phase: everything except the application

With `CONTAINER_IMAGE` unset the parameter file sets `deployApplication=false`: no Container App,
jobs or SWA link yet (Container Apps resolve Key Vault references at creation, so the secrets must
exist first).

```bash
az deployment group what-if  -g "$RG" -n "main-$ENV" \
  -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"
az deployment group create   -g "$RG" -n "main-$ENV" \
  -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"

out() { az deployment group show -g "$RG" -n "main-$ENV" --query "properties.outputs.$1.value" -o tsv; }
KV=$(out keyVaultName); ACR=$(out containerRegistryName); PG=$(out postgresServerName)
IDENTITY=$(out identityName); SWA_HOST=$(out staticWebAppHostname)
echo "$KV $ACR $PG $IDENTITY $SWA_HOST"
```

## 4. Key Vault secrets

```bash
# Django SECRET_KEY: generated locally, written through a 0600 temp file, never echoed.
tmp=$(mktemp) && chmod 600 "$tmp"
python -c "import secrets; print(secrets.token_urlsafe(64), end='')" > "$tmp"
az keyvault secret set --vault-name "$KV" --name django-secret-key --file "$tmp" --output none
rm -f "$tmp"
```

`entra-client-secret` is written by `create-entra-app` in step 5. (`database-password` is only
needed with `DB_AUTH_MODE=password`, which this template does not use.)

## 5. Entra External ID app registration

Follow `docs/entra-setup.md` §1–3 with `--public-url "https://$SWA_HOST"` and `--key-vault "$KV"`.
Then export the printed values for the second phase:

```bash
export ENTRA_AUTHORITY=https://<tenant-subdomain>.ciamlogin.com/<external-tenant-id>
export ENTRA_TENANT_ID=<external-tenant-id>
export ENTRA_CLIENT_ID=<application-client-id>
```

## 6. PostgreSQL: Entra admin, database, managed-identity role

```bash
infrastructure/scripts/setup-postgres-entra.sh \
  --resource-group "$RG" --server "$PG" --identity-name "$IDENTITY" --database medical \
  --allow-current-ip
```

It sets you (or `--admin-object-id/--admin-name/--admin-type Group`) as Entra administrator,
creates database `medical` owned by that administrator, creates the identity's role with
`pgaadauth_create_principal_with_oid` (not an admin), grants `CONNECT, CREATE, TEMPORARY` on the
database and `USAGE, CREATE` on schema `public`, and removes the temporary firewall rule on exit.
With private networking, run it from a machine inside the VNet (no `--allow-current-ip`).

## 7. Second phase: image + application

```bash
LOGIN_SERVER=$(az acr show -n "$ACR" --query loginServer -o tsv)
TAG=$(git rev-parse HEAD)
docker build --target runtime -t "$LOGIN_SERVER/medical-backend:$TAG" backend/
az acr login -n "$ACR"
docker push "$LOGIN_SERVER/medical-backend:$TAG"

export CONTAINER_IMAGE="$LOGIN_SERVER/medical-backend:$TAG"   # → deployApplication=true
az deployment group create -g "$RG" -n "main-$ENV" \
  -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"

APP=$(out containerAppName); MIGRATE=$(out migrateJobName)
EXEC=$(az containerapp job start -n "$MIGRATE" -g "$RG" --query name -o tsv)
az containerapp job execution show -n "$MIGRATE" -g "$RG" --job-execution-name "$EXEC" \
  --query properties.status -o tsv            # repeat until Succeeded
curl -fsS "https://$(out containerAppFqdn)/api/ready/"
```

The first revision starts before the migrate job ran; its readiness probe (`/api/ready/` only
checks connectivity) passes, but requests fail until the migration finishes — on the very first
deployment only. Every later deployment runs the job first (`backend.yml`).

## 8. Frontend

```bash
cd frontend && npm ci && npm run build && cd ..
TOKEN=$(az staticwebapp secrets list -n "$(out staticWebAppName)" -g "$RG" --query properties.apiKey -o tsv)
npx --yes @azure/static-web-apps-cli@2 deploy frontend/dist --deployment-token "$TOKEN" --env production
unset TOKEN
```

(`frontend.yml` does the same with the official action and an OIDC-read token.) Open
`https://$SWA_HOST/`, sign in, then grant the first administrator (step 9).

## 9. Granting the admin role

```bash
az containerapp exec -n "$APP" -g "$RG" --command "python manage.py grant_admin <email-or-oid>"
```

The user must have signed in once (the account exists only after the first sign-in). The grant is
audited. Add the person to the `medical-admins-<env>` group so the MFA policy applies
(`docs/entra-setup.md` §4).

## 10. Enabling OCR (only after legal decisions L2/L3)

```bash
export ENABLE_OCR=true          # or the GitHub variable ENABLE_OCR=true
az deployment group create -g "$RG" -n "main-$ENV" \
  -f infrastructure/main.bicep -p "infrastructure/parameters/$ENV.bicepparam"
```

This deploys Azure OpenAI (keys disabled) with a `gpt-4o` deployment (`openAiDeploymentSkuName`
`Standard` = processed in the resource's region; `openAiLocation` if the model is not offered in
the main region), grants the identity *Cognitive Services OpenAI User*, and sets `OCR_ENABLED=true`,
`OCR_PROVIDER=azure_openai`, `AZURE_OPENAI_*`. Check model availability and quota in the region
first (`az cognitiveservices model list -l <region>`). Disabling: unset `ENABLE_OCR` and redeploy
(the account is no longer referenced; delete it with `az cognitiveservices account delete` and
purge it if the data must go).

## Deployment-time migrations (§37)

- `backend.yml` → `reusable-deploy-backend.yml`: push image → `az containerapp job update --image`
  + `az containerapp job start` on the **migrate** job → wait for `Succeeded` → update the cleanup
  job → `az containerapp update --image` (new revision) → wait until the revision is `Healthy` →
  smoke test. Replicas never migrate (`entrypoint.sh web` refuses `RUN_MIGRATIONS_ON_START`).
- The migrate job runs `migrate --noinput` then `createcachetable` (shared rate-limit cache,
  `CACHE_URL=dbcache://django_cache`).
- While the job runs, the **previous revision keeps serving** against the migrated schema, so every
  migration must be backward compatible (expand/contract, `django-safe-migration`): add nullable
  columns / new tables first; backfill; switch code; drop old columns in a later release.
- A failed migration stops the pipeline before the app is touched. Fix forward with a new
  migration; never edit an applied one.

### Rolling back

```bash
# Application only (schema unchanged or still compatible): previous image as a new revision
az containerapp revision list -n "$APP" -g "$RG" \
  --query "[].{name:name, image:properties.template.containers[0].image, created:properties.createdTime}" -o table
az containerapp update -n "$APP" -g "$RG" --image <previous-image>
```

Do not reverse migrations in production as a rollback (data loss risk); because migrations are
expand/contract, the previous image works on the newer schema. If a migration damaged data,
restore the database (below) to a new server and repoint `DATABASE_URL`.

## Backups and recovery (§48)

> **NOT VERIFIED — requires Azure credentials.** The protection settings are in the templates
> (checked by `check-template-security.py`); no restore has been run against Azure yet. The
> first restore drill (below) is part of going live.

### What is protected (configured by Bicep)

| Store | Protection | dev | staging | prod | Parameter |
|---|---|---|---|---|---|
| PostgreSQL | automated backups + point-in-time restore (PITR) | 7 days | 14 days | 35 days | `postgresBackupRetentionDays` |
| PostgreSQL | geo-redundant backup (restore in the paired region) | off | off | **on** | `postgresGeoRedundantBackup` |
| PostgreSQL | zone-redundant high availability | off | off | off (enable when the RTO requires it; doubles compute) | `postgresHighAvailabilityMode` |
| Blob documents | soft delete for blobs **and** the container | 7 days | 14 days | 14 days | `blobSoftDeleteRetentionDays` |
| Blob documents | versioning; previous versions deleted by a lifecycle rule after | 30 days | 30 days | 90 days | `blobPreviousVersionRetentionDays` |
| Blob documents | redundancy | LRS | LRS | ZRS | `storageSkuName` |
| Key Vault | soft delete + **purge protection** | 7 days | 30 days | 90 days | `keyVaultSoftDeleteRetentionDays` (fixed at creation) |
| Configuration | Bicep, workflows and scripts in Git; images in ACR tagged with the commit SHA | | | | |

Not backed up: Application Insights / Log Analytics data (retention only), the Entra External ID
tenant (users live there; Microsoft operates it), and the Container App itself (stateless,
redeployed from Git + ACR). Documents are restored in two parts: PostgreSQL holds the
`documents_document` rows, Blob Storage the files.

### RPO / RTO assumptions (to be confirmed by the organization)

| Scenario | RPO (data loss) | RTO (time to service) | Procedure |
|---|---|---|---|
| Bad deployment, schema intact | 0 | ~10 minutes | previous image (*Rolling back*) |
| Data damaged by a bug or an operator | ≤ 5 minutes before the damage (PITR) | 1–2 hours | A |
| Deleted or overwritten document | 0 within the soft-delete / version window | minutes | B |
| Deleted Key Vault secret or vault | 0 within the soft-delete window | minutes | C |
| Region outage (prod) | ≤ 1 hour (geo-backup lag) | several hours: new environment in the paired region | D |

### A. Restore PostgreSQL to a point in time

PITR always creates a **new server**; the original stays untouched until you switch.

```bash
# 0. Stop writes: scale the app to zero and move the nightly cleanup job far into the future
#    (it would purge blobs whose rows are newer than the restore point).
az containerapp update -n "$APP" -g "$RG" --min-replicas 0 --max-replicas 0
az containerapp job update -n "$(out cleanupJobName)" -g "$RG" --cron-expression "0 0 1 1 *"

# 1. Restore to a new server (UTC timestamp just before the damage)
az postgres flexible-server restore -g "$RG" --name "$PG-restored" \
  --source-server "$PG" --restore-time "2026-10-06T08:00:00Z"

# 2. Entra admin + the identity's role and grants on the new server
infrastructure/scripts/setup-postgres-entra.sh --resource-group "$RG" --server "$PG-restored" \
  --identity-name "$IDENTITY" --database medical --allow-current-ip

# 3. Point the app and both jobs at the new server
NEW_URL="postgres://$IDENTITY@$PG-restored.postgres.database.azure.com:5432/medical"
az containerapp update -n "$APP" -g "$RG" --set-env-vars "DATABASE_URL=$NEW_URL"
for job in "$(out migrateJobName)" "$(out cleanupJobName)"; do
  az containerapp job update -n "$job" -g "$RG" --set-env-vars "DATABASE_URL=$NEW_URL"
done

# 4. Reopen with the environment's replica values, check, restore the cleanup schedule
az containerapp update -n "$APP" -g "$RG" --min-replicas 1 --max-replicas 5
curl -fsS "https://$(out containerAppFqdn)/api/ready/"
az containerapp job update -n "$(out cleanupJobName)" -g "$RG" --cron-expression "30 1 * * *"
```

Then make the switch permanent: the next `az deployment group create` sets `DATABASE_URL` from
the template's server name again, so either keep deploying with the original server (restore its
data from the restored one with `pg_dump`/`pg_restore` during a maintenance window) or change
the server name in `main.bicep`. Delete the damaged server only after the restored data is
accepted. Documents uploaded after the restore point have blobs without rows; the cleanup job
removes them after `BLOB_CLEANUP_GRACE_HOURS` (still recoverable as soft-deleted blobs).

Geo-restore (prod, region loss) — new server in the paired region, then procedure D:

```bash
az postgres flexible-server geo-restore -g <rg-in-paired-region> --name "$PG-geo" \
  --source-server "$(az postgres flexible-server show -g "$RG" -n "$PG" --query id -o tsv)" \
  --location <paired-region>
```

### B. Restore a document (Blob Storage)

Shared-key access is disabled, so every command uses `--auth-mode login`; the operator needs
*Storage Blob Data Contributor* on the account for the duration of the restore (grant it, then
remove it). The blob name is `documents_document.blob_name`.

```bash
ACCOUNT=$(out storageAccountName)
# deleted blob (within the soft-delete window)
az storage blob undelete --account-name "$ACCOUNT" -c medical-documents -n "<blob_name>" --auth-mode login
# overwritten blob: list the versions, then put the wanted version back as the current one
az storage blob list --account-name "$ACCOUNT" -c medical-documents --prefix "<blob_name>" \
  --include v --auth-mode login -o table
az storage blob download --account-name "$ACCOUNT" -c medical-documents -n "<blob_name>" \
  --version-id "<version-id>" -f restored.bin --auth-mode login
az storage blob upload --account-name "$ACCOUNT" -c medical-documents -n "<blob_name>" \
  -f restored.bin --overwrite --auth-mode login && rm -f restored.bin
# deleted container (within the container soft-delete window)
az storage container list --account-name "$ACCOUNT" --include-deleted --auth-mode login -o table
az storage container restore --account-name "$ACCOUNT" -n medical-documents \
  --deleted-version "<deleted-version>" --auth-mode login
```

The downloaded file is personal data: use an encrypted operator machine and delete it right after
the upload.

### C. Recover Key Vault secrets

```bash
az keyvault secret list-deleted --vault-name "$KV" -o table
az keyvault secret recover --vault-name "$KV" --name django-secret-key
az keyvault recover --name "$KV"                       # a deleted vault
```

Purge protection means nobody, not even an Owner, can purge a deleted vault or secret before its
retention ends. Restart the active revision so Container Apps re-reads a recovered secret
(`docs/entra-setup.md` §5).

### D. Rebuild an environment

Everything except data is in Git: create a resource group (another region if needed) and follow
steps 1–9 above, with the geo-restored or PITR server as the database (adjust `DATABASE_URL` as
in procedure A). Re-run `create-entra-app` with the new public URL. Blob data has no cross-region
copy with LRS/ZRS; if the organization requires one, switch prod to `Standard_GZRS` (cost
decision, not configured).

### Restore drill (once per quarter, in staging)

1. Note the time `T`; create a test application with two documents in staging and submit it.
2. Delete one beneficiary in the database copy you will discard (or through the UI on a draft)
   and delete one document through the UI.
3. Run procedure A to `T + 1 minute` and procedure B for the deleted blob.
4. Verify: the application opens in the admin UI with both documents, the fee snapshot and the
   audit history; `/api/ready/` is green; the migrate job reports `No migrations to apply`.
5. Record the measured RPO/RTO and every problem in `docs/progress.md` and update the table above.
6. Delete the restored server, or keep it as the new staging server and redeploy accordingly.

## Production upgrade path (§34)

The default is a secure MVP: PostgreSQL accepts only Azure-internal connections (`0.0.0.0` rule)
plus Entra tokens + TLS; Blob and Key Vault have public endpoints but no anonymous/shared-key
access; Azure OpenAI has keys disabled. `enablePrivateNetworking=true` (decide **before** the
first prod deployment) adds a VNet with a delegated Container Apps subnet, a VNet-integrated
PostgreSQL server without public access, and private endpoints + private DNS for Blob, Key Vault
and OpenAI (their public network access disabled). Operators then need a jump host / VPN in the
VNet for `setup-postgres-entra.sh` and Key Vault secret changes; Container Registry stays public
(Basic/Standard have no private endpoints; Premium does). Further steps: Microsoft Defender for
Storage malware scanning (L8), Defender for Cloud, alerts on 5xx rate / job failures, Front Door
WAF in front of the Static Web App if required.

## Cost (§52)

Retail list prices, USD, `westeurope`, read from the Azure Retail Prices API on 2026-10-06
(prices vary by region and change; use the Azure pricing calculator for a quote). 730 h/month.

| Component | dev default | prod default | Price basis |
|---|---|---|---|
| Static Web Apps | Standard | Standard | $9 / app / month (+ $0.20/GB over 100 GB) |
| Container Apps app | 0.5 vCPU / 1 GiB, **min 0** (scales to zero) | 1 vCPU / 2 GiB, min 1, max 5 | active vCPU $0.000034/s, idle vCPU $0.000004/s, memory $0.000004/GiB-s; $0.56 per million requests. One always-on prod replica ≈ $31/month idle, ≈ $110/month fully busy; the monthly free grant per subscription reduces this |
| Container Apps jobs | migrate per deploy, cleanup nightly | same | billed per execution second at the same rates (cents per month) |
| Container Apps environment | 1 | 1 | the price list now shows an *Environment Management Hour* meter ($0.143/h ≈ $104/month, effective 2026-09-01); whether it applies to Consumption-only environments is **NOT VERIFIED** — check before relying on scale-to-zero savings |
| PostgreSQL compute | Burstable B1ms | General Purpose D2ds_v5 | B1ms $0.0199/h ≈ $14.5/month; B2s (staging) $0.0796/h ≈ $58; D2ds_v5 $0.212/h ≈ $155; zone-redundant HA doubles compute |
| PostgreSQL storage/backup | 32 GB, 7-day PITR | 64 GB, 35-day PITR, geo-redundant | storage per provisioned GB; backup storage beyond the free 100 % of provisioned size $0.103/GB-month (LRS), geo-redundant backup costs more |
| Container Registry | Basic | Standard | Basic $0.1666/day ≈ $5/month; Standard $0.6666/day ≈ $20/month |
| Blob Storage | LRS hot | ZRS hot | per GB stored + transactions; ID images are small (≤ 10 MB each); versions/soft delete add stored GB |
| Log Analytics | 1 GB/day cap, 30 days | no cap, 90 days | $2.99/GB ingested (Analytics Logs); the largest variable cost after PostgreSQL — keep `LOG_LEVEL=INFO`, no request bodies |
| Key Vault | standard | standard | per 10 000 operations (Container Apps cache references; negligible) |
| Azure OpenAI (optional) | off | off until L2 | per input/output token per OCR call (image tokens dominate); `openAiCapacity` caps throughput, not cost |
| Private networking (optional) | off | decide | private endpoints per hour + per GB, private DNS zones; Container Registry Premium if it must be private too |

**Cheapest reasonable dev:** the `dev.bicepparam` defaults — scale-to-zero app, B1ms, Basic ACR,
LRS, 1 GB/day log cap, no OCR, no private networking. Static Web Apps Standard is kept because the
linked backend (same-origin cookies, §4.1) requires it; the Free plan has no linked backend.

**Initial production configuration** (`prod.bicepparam`): Container App 1 vCPU / 2 GiB, 1–5
replicas, 3 Gunicorn workers; PostgreSQL General Purpose D2ds_v5, 64 GB, 35-day PITR,
geo-redundant backup, HA off; Storage ZRS; ACR Standard; Log Analytics 90 days without a daily
cap; Application Insights with Entra-only ingestion; OCR off; private networking decided before
the first deployment (recommended on). Order of magnitude at the list prices above: PostgreSQL
≈ $155 + storage/backup, Container Apps ≈ $31–110, ACR ≈ $20, SWA $9, Log Analytics a few dollars
per GB ingested, plus the environment meter if it applies (Q-T16) — roughly **$250–350 per
month** before private networking and OCR. This is an estimate, not a quote.

### Cost drivers (PROMPT.md §52)

| Driver | What makes it grow | How to control it |
|---|---|---|
| **PostgreSQL compute** | the SKU runs 24/7 whatever the traffic; HA doubles it | Burstable for dev/staging, General Purpose only in prod; stop an unused dev server (`az postgres flexible-server stop`); HA only when the RTO requires it |
| **PostgreSQL storage and backups** | provisioned GB (not used GB); backup storage above 100 % of the provisioned size; geo-redundant backup stores a second copy | start at 32/64 GB (storage can only grow); keep retention at what the RPO needs (7/14/35 days) |
| **Container Apps vCPU-seconds and min replicas** | `minReplicas ≥ 1` bills idle time all month; active time per vCPU-second and GiB-second; jobs per execution second | dev scales to zero (`minReplicas = 0`; the first request after idle is slow); raise `maxReplicas` for peaks rather than the minimum |
| **Static Web Apps Standard** | flat per app per month + bandwidth above 100 GB | one app per environment; Standard only because the linked backend needs it |
| **Blob storage and transactions** | stored GB (documents + previous versions + soft-deleted blobs), read/write operations; ZRS costs more than LRS | 8 MB upload cap and per-user upload limit; lifecycle rule deletes old versions; the cleanup job purges orphans |
| **Log Analytics ingestion** | GB ingested per day (requests, dependencies, logs) and retention beyond the included period | `LOG_LEVEL=INFO`, no bodies, Gunicorn access log off; daily cap in dev/staging (`logAnalyticsDailyQuotaGb`); Application Insights sampling if traffic grows |
| **Azure OpenAI tokens per OCR call** | one image per call (image tokens dominate) + up to 1 000 output tokens; cost = calls × tokens × model price | off by default; only on the doctor's click, one call per document, 30 calls per user per hour; pick the smallest vision model that reads Arabic IDs reliably |
| **Private networking** | private endpoints (per hour + per GB), private DNS zones, VNet-integrated PostgreSQL; ACR Premium if the registry must be private too | off in dev/staging; a security decision for prod (`ENABLE_PRIVATE_NETWORKING`) |
| **Container Apps environment** | possible *Environment Management Hour* meter (Q-T16) | check the first month's bill |
| **Key Vault** | operations (negligible: Container Apps caches the references) | — |

**Increase as traffic grows:** `maxReplicas` and `httpConcurrency` first (seasonal peaks), then
`containerCpu/Memory` + `gunicornWorkers`; PostgreSQL `postgresSkuName` (D4ds_v5) and
`postgresHighAvailabilityMode=ZoneRedundant` when the RTO requires it; storage auto-grows.
Never trade away TLS, Entra auth, private containers or backups to save cost.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Container App creation fails with a Key Vault reference error | Secrets missing (step 4/5) or the identity's *Key Vault Secrets User* assignment not yet propagated — wait a few minutes and redeploy. |
| Revision never becomes ready; logs show `ImproperlyConfigured` | A required setting is empty (`ENTRA_*`, secrets). Production settings refuse to start on purpose. |
| `password authentication failed for user "id-medsyn-<env>"` | Step 6 not run, wrong `AZURE_CLIENT_ID` on the app (must be the user-assigned identity's client id — the template sets it), or token for another tenant. |
| Blob `403 AuthorizationPermissionMismatch` | Role assignment still propagating, or `BLOB_ACCOUNT_URL` points at another account. Shared-key access is disabled by design. |
| SAS document links fail | *Storage Blob Delegator* missing on the account (user-delegation key). |
| CSRF failure on POST | The browser origin is not in `CSRF_TRUSTED_ORIGINS` (custom domain not set as `publicHostname`). |
| Cookies not sent / 401 after sign-in | The SPA is not served from the same origin as `/api` (linked backend missing — check `static-web-app-link`). |
| `DisallowedHost` | The Host header Django sees behind the linked backend is not in `ALLOWED_HOSTS` (Q-T13): add it via `publicHostname` or extend `allowedHosts` in `main.bicep`. |
| OCR `OCR_UNAVAILABLE` | Model deployment missing/quota exhausted (`429`), or *Cognitive Services OpenAI User* not propagated. |
