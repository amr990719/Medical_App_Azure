# Azure deployment

Exact commands for the dev environment, and the reference behind production (PROMPT.md §33–§37,
§48, §52). **Production is created and operated through `docs/production-runbook.md`**, and accepted
through `docs/production-acceptance.md`. Environments are dev and prod only. Architecture:
`docs/architecture.md`. CI/CD: `docs/github-setup.md`. Sign-in: `docs/entra-setup.md`.

Commands are Bash (Git Bash or WSL on Windows). The same steps in Windows PowerShell are in
`README.md` §9–§14.

## Verification status

**dev was deployed with these steps on 2026-10-07/08 and is deployed by GitHub Actions since
2026-10-09** (resource group `Medical_App`, uaenorth; Static Web App in eastasia, D140). Session
logs: `docs/progress.md` Sessions 11–13. **prod has never been deployed.** There is no staging (owner, 2026-11-05). This table
is about dev; production's record is `docs/production-acceptance.md`.

| Step / capability | dev | How it was checked |
|---|---|---|
| §3 first phase, §7 second phase (Bicep) | verified | what-if then `az deployment group create` Succeeded (6 min 14 s / 4 min 48 s); CI deploys since merge `8164960` |
| §4 Key Vault secrets + Container Apps Key Vault references | verified | `django-secret-key` and `entra-client-secret` set; the app starts and completes the Entra code exchange with them |
| §5 Entra app registration | verified | `create-entra-app.ps1`; real sign-in through the SWA host (Session 12) |
| §6 PostgreSQL Entra admin + managed-identity role | verified | `/api/ready/` → `{"status": "ok", "database": "ok"}` through the SWA host (re-checked 2026-10-11) |
| Migrate job | verified | executions Succeeded on every deploy (latest deploy 2026-10-24, image `010cbb8`, applied `beneficiaries.0002`, `documents.0003`, `fees.0003`–`0006`; read back with a one-off execution); `grant_admin` run as a job execution |
| SWA linked backend, same-origin `/api` | verified | `/api/health/`, `/api/ready/` 200 and the §46 401 envelope via the SWA host; the Container App FQDN answers 401 (SWA auth on the link) |
| GitHub OIDC deploy identity, AcrPush, SWA token read | verified | `backend`, `infrastructure`, `frontend` deploy-dev jobs succeeded (runs `37990842638`, `37990842692`, `37988694152`) |
| Blob upload + user-delegation SAS | **NOT VERIFIED** | needs a signed-in doctor (owner's Entra account) |
| Full doctor → admin flow on Azure | **NOT VERIFIED** | same; covered locally by Playwright `e2e.yml` on every PR |
| App Insights ingestion / Log Analytics queries | verified (2026-10-11) | requests, traces and dependencies arrive; a request to the new revision was queryable about 1 s after it was sent; 0 unmasked 14-digit runs in 30 days. Queried through the ARM endpoint, see §"Telemetry verification" |
| Admin sign-in with MFA (`amr`, Conditional Access) | **NOT VERIFIED** | dev runs with `ENTRA_ADMIN_REQUIRE_MFA=False` (D144) |
| §10 OCR with Azure OpenAI | **NOT VERIFIED** | not deployed (off in production by owner decision, D150) |
| Private networking (`enablePrivateNetworking`) | **NOT VERIFIED** | dev uses public endpoints + Entra-only auth |
| Restore drill (§"Backups and recovery") | **NOT VERIFIED** | never run |
| Cleanup job (scheduled) | deployed; a run not checked | — |
| §11 Doctor notifications: deploy, env wiring, `notify` job | verified (2026-11-04) | run `41849338442` (image `c5958d0`, `allowlist`, email only) succeeded 14:44 UTC; health 200; app and `notify` job carry the 8 notification env names and no `WHATSAPP_*`; migrate and cleanup carry none; job cron `*/5 * * * *`; first two scheduled executions (14:45, 14:50 UTC) Succeeded |
| §11 `notify_run` telemetry from the job | verified for an empty run | one `notify_run` trace per execution (role `medical-notify`, two seen) with every count 0 (before the real test) reached Application Insights and the job console, so the telemetry start in `manage.py` works on Azure |
| §11 Real send through SES | verified (2026-11-04) | the owner's real email test on dev worked and the emails reached the owner's inbox; the job's `notify_run` telemetry recorded 4 sent and no `notification_failed` traces |
| §11 Email authentication (SPF, DKIM, DMARC) | verified (2026-11-04) | owner-observed: the owner's real test emails arrived and all three results were PASS |
| §11 `notifications@neqabacare.com` forward (Cloudflare) | verified (2026-11-05) | owner-observed: an email sent to that address reached the owner's inbox |
| §11 Bounce handling, allowlist suppression on Azure, failure and expiry paths | **NOT VERIFIED** | not exercised yet |
| §11 Alert rules and action group deployed | verified (2026-11-05) | read-only `az` checks: the four `alert-medsyn-dev-notify-*` rules are enabled and send to `ag-medsyn-dev-notify`, whose receiver status is `Enabled`; the rules were created 2026-11-04 15:49 UTC, during run `41861057067` (merge of the `secrets: inherit` fix, `419f68a`) |
| §11 Each alert actually firing, an alert email arriving | **NOT VERIFIED** | as of 2026-11-05 no alert has fired and no alert email has been seen. The test-email API rejected all 4 attempts on 2026-11-05 with "There are no valid receivers in the request" (CLI and REST); cause unknown (Q-N17 in `docs/progress.md`) |
| §11 Meta / WhatsApp | parked | `enableWhatsApp` stays off |
| `release-production.yml`, `bootstrap-production.sh`, `cutover-domain.sh`, `recovery.sh`, `service-alerts.bicep`, `RECOVERY_HOLD`, `POSTGRES_SERVER_NAME_OVERRIDE`, digest-pinned images | **NOT VERIFIED — requires Azure credentials** | written and tested locally (2026-11-05); promotion tested against local registries; never run on Azure |

Static checks still apply to every environment: Bicep builds and lints with zero warnings (strict
`infrastructure/bicepconfig.json`), and `check-template-security.py` passes in CI.

## What gets deployed (per environment, one resource group)

| Module | Resource | Notes |
|---|---|---|
| `identity.bicep` | user-assigned identity `id-medsyn-<env>` | used by the app and its jobs for Blob, Key Vault, PostgreSQL, ACR, OpenAI, App Insights |
| `monitoring.bicep` | Log Analytics + Application Insights | retention / daily cap / Entra-only ingestion parameters. Has no alerts of its own |
| `service-alerts.bicep` | availability test, its separate `appi-…-uptime` component, action group, metric and log alerts | only with `enableServiceAlerts` (prod), `alertEmail` and the deployed app. Table: `docs/production-runbook.md`, "Monitoring" |
| `notification-alerts.bicep` | four alert rules on the notify job | with `enableNotifications` and `alertEmail` |
| `key-vault.bicep` | Key Vault (RBAC, soft delete, purge protection) | secrets set by you, never by Bicep |
| `storage.bicep` | Storage account + private container `medical-documents` | no public access, **shared keys disabled**, TLS 1.2, soft delete, versioning, lifecycle for old versions |
| `postgres.bicep` | PostgreSQL Flexible Server 16 | Entra auth on, password auth off by default, TLS ≥ 1.2 required, PITR + optional geo backup / HA |
| `container-registry.bicep` | Container Registry | no admin user, no anonymous pull |
| `container-apps-env.bicep` | Container Apps environment (workload profiles, Consumption) | logs to Log Analytics |
| `container-app.bicep` | Django app + `migrate` job (manual) + `cleanup` job (cron) + `notify` job (cron, with `enableNotifications`) | Key Vault references, probes on `/api/health/` + `/api/ready/`, HTTP-concurrency scaling. With `deployWebApp=false`, only the migrate job exists |
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
- **Region.** The owner's choice (`docs/security.md` L3); production assumes `uaenorth`, as on dev, to
  be confirmed before its first deployment. All resources except the Static Web App use the
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
ENV=dev                                   # for prod, use the bootstrap in docs/production-runbook.md
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
```

Check it through the Static Web App once the frontend is deployed (step 8). The Container App's own
address answers 401, because the Static Web App link protects it:

```bash
curl -fsS "https://$SWA_HOST/api/ready/"      # {"status": "ok", "database": "ok", "schema": "ok"}
```

On dev's first deployment, the revision started before the migrate job ran, and requests failed until
it finished. With these commands that would still happen, and `/api/ready/` would now answer 503
meanwhile. **Production avoids it:** the bootstrap deploys with `deployWebApp=false`, so only the migrate
job exists until the schema does. Every later deployment runs the job first.

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

The user must have signed in once (the account exists only after the first sign-in). Run
`grant_admin <email-or-oid>` as a one-off command (below). The grant is audited
(`ADMIN_ROLE_GRANTED`) and ends the user's sessions. `revoke_admin <email-or-oid>` is the audited
reverse (`ADMIN_ROLE_REVOKED`); it refuses to remove the last active administrator. Add the person
to (or remove them from) the `medical-admins-<env>` group so the MFA policy applies
(`docs/entra-setup.md` §4).

### One-off management commands

`az containerapp exec` needs an interactive terminal (it fails from scripts and CI), so start an
execution of the **migrate** job with only the container arguments replaced. The image, the
environment and the secret references stay those of the job. `entrypoint.sh` runs any arguments
that are not `web`/`migrate`/`cleanup`/`notify` as given. The migrate job has no notification
settings, so nothing run this way can send.

`infrastructure/scripts/run-job-command.sh` does all of this and waits for the result (NOT VERIFIED on
Azure yet):

```bash
infrastructure/scripts/run-job-command.sh --job "$MIGRATE" --resource-group "$RG" \
  -- python manage.py grant_admin <email-or-oid>
```

| Command | What it does |
|---|---|
| `grant_admin`, `revoke_admin` | section 9 |
| `release_check [--fiscal-year N] [--skip-blob] [--require-admin]` | what a web request cannot check: migrations, shared cache, explicit fiscal year, fee schedule, reference data, a blob round trip, Entra discovery. Exits 1 on any failure |
| `reconcile_documents [--restored-to <ISO8601>] [--limit N]` | read only: rows without bytes, blobs without rows, and which of those are newer than a restore point. Exits 1 when bytes are missing |
| `reconcile_notifications --restored-to <ISO8601> [--apply]` | after a restore, ends in-flight rows `SUPERSEDED` so nothing sends twice. Dry run by default. Through this job it cannot see the sending mode, so pause sending first (`recovery.sh` checks) |
| `alert_test` | emits the one harmless trace that fires the `ops-alert-test` rule: proves an alert reaches a person |

The dev grant ran as a job execution in Session 12 (execution `caj-medsyn-dev-migrate-myfcr7j`). The
long form, which that script automates:

```bash
JOB_ID=$(az containerapp job show -n "$MIGRATE" -g "$RG" --query id -o tsv)
az rest --method get --url "https://management.azure.com${JOB_ID}?api-version=2025-01-01" \
  --query "{containers: properties.template.containers}" -o json > start.json   # no secret values
python -c "import json; b = json.load(open('start.json')); b['containers'][0]['args'] = ['python', 'manage.py', 'grant_admin', '<email-or-oid>']; json.dump(b, open('start.json', 'w'))"
EXEC=$(az rest --method post --url "https://management.azure.com${JOB_ID}/start?api-version=2025-01-01" \
  --body @start.json --query name -o tsv)
az containerapp job execution show -n "$MIGRATE" -g "$RG" --job-execution-name "$EXEC" \
  --query properties.status -o tsv            # repeat until Succeeded
CONTAINER=$(az containerapp job show -n "$MIGRATE" -g "$RG" --query 'properties.template.containers[0].name' -o tsv)
az containerapp job logs show -n "$MIGRATE" -g "$RG" --execution "$EXEC" --container "$CONTAINER"
rm start.json
```

`az containerapp job logs show` needs the `containerapp` CLI extension. Do not use `job start
--image …` for this: overriding the image there can drop the job's environment.

## 10. Enabling OCR (dev only; production pins it off, D150)

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

## 11. Enabling doctor notifications (email now, WhatsApp later)

Design: `docs/superpowers/specs/2026-11-02-notifications-design.md` (section 14 for the email-first
decision of 2026-11-04). What has been verified on dev is in the status table above. Nothing has run
on production: its stages are in `docs/production-runbook.md`, "Notifications". Creating Azure, AWS or
Meta resources and sending a real message each need the owner's confirmation at that step. Moving
production to `notificationsMode=live` is the owner's decision. The owner declined formal legal
sign-off and the AWS CloudWatch reputation alarms on 2026-11-05; that is recorded, not a gate
(`docs/security.md` §0).

**Email only is the supported setup.** Amazon SES is the only channel in use. WhatsApp is parked
behind `WHATSAPP_ENABLED` (off by default) until the Meta business profile is finished; its steps
are in "Later: turning WhatsApp on" below.

### Email only

| Phase | Work | Done when |
|---|---|---|
| 1 | SES: sending domain verified (DKIM, custom MAIL FROM, DMARC; Cloudflare records DNS only), a monitored `notifications@` mailbox, production access in the selected Region | domain verified, production access granted |
| 2 | Deploy the code (this repository) with `enableNotifications=false` | migrate job succeeded |
| 3 | Dev trial: `enableNotifications=true`, `notificationsMode=allowlist` with the owner's address only | each event seen in an inbox, a provider failure reaches each alert, a paused job raises the missed-run alert |
| 4 | Production: off, then an allowlist trial, then `notificationsMode=live` (`docs/production-runbook.md`) | owner decision |

**Credentials.** Federation (Task 14) is not built, so the app and the notify job read an AWS access
key from the environment. Production settings refuse to start in `allowlist` or `live` with real
providers when `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is missing, and the message names the
setting, never a value. **Long-lived keys are the spec's fallback**: use an IAM user limited to
`ses:SendEmail` on the one identity, rotate the key about every 90 days, and move to federation (Task 14,
the preferred path) when it exists. To rotate: create the new key first, then update both Key Vault
secrets (`aws-access-key-id` and `aws-secret-access-key`) together and restart; a mismatched pair
fails every send as a temporary `SignatureDoesNotMatch` or `IncompleteSignature` until fixed. Delete
the old key afterwards (NOT VERIFIED).

**Key Vault secrets that must exist before `enableNotifications=true`.** The Container Apps secret
references are Key Vault references, so a missing secret is expected to stop the app and the job
from starting (NOT VERIFIED). Names only here; values never in Git or the shell history (write
them from a 0600 temp file as in step 4):

| Secret | Needed when | Holds |
|---|---|---|
| `aws-access-key-id` | `sesAccessKeyFromKeyVault=true` | the AWS access key ID |
| `aws-secret-access-key` | `sesAccessKeyFromKeyVault=true` | the AWS secret access key |
| `notifications-allowlist` | `notificationsMode=allowlist` only | comma-separated addresses allowed in `allowlist` mode |

In `off` and `live` nothing references `notifications-allowlist`, and no `whatsapp-*` secret is
referenced unless `enableWhatsApp=true`.

Deploy parameters of `infrastructure/main.bicep`. `dev.bicepparam` and `prod.bicepparam` read six of
them from the GitHub environment, so a later deployment keeps them instead of undoing a hand-passed
one. Variables: `ENABLE_NOTIFICATIONS`, `NOTIFICATIONS_MODE`, `SES_ACCESS_KEY_FROM_KEY_VAULT`,
`SES_REGION`, `SES_FROM_ADDRESS`; environment **secret**: `ALERT_EMAIL` (a secret so the what-if log
masks it). All unset means off (`false`, `off`, blank). The rest can be passed at deploy time, with
non-secret values only:

| Parameter | Meaning |
|---|---|
| `enableNotifications` | default `false`; creates the `notify` job and the settings and secret references on the app and the job |
| `notificationsMode` | `off` (default), `allowlist` or `live`; set on the app and the `notify` job only. The `migrate` and `cleanup` jobs get none of the notification settings or secrets and stay at `off`/`fake`, because production settings refuse to import with a sending mode and no secrets |
| `sesAccessKeyFromKeyVault` | default `false`; `true` injects `aws-access-key-id` and `aws-secret-access-key` as `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` on the app and the notify job only. Required in practice until Task 14 exists |
| `sesRegion`, `sesFromAddress` | SES identity Region and sender address |
| `notificationBaseUrl` | link base in messages; empty uses the public host |
| `notifyCron` | UTC cron of the job, default `*/5 * * * *` |
| `alertEmail` | when set, deploys the four alert rules (failed or expired notification, oldest due row over 30 minutes, no `notify_run` in 15 minutes, job failed), and the service alerts on prod. From the secret `ALERT_EMAIL`; not committed |
| `awsRoleArn`, `awsWebIdentityAudience` | IAM role and audience for the federation, **NOT VERIFIED** (Task 14 is deferred; leave blank) |
| `notificationMaxAgeHours`, `notificationResendRateLimit` | optional; left blank the application defaults (72 h, 30/hour) apply |
| `enableWhatsApp` | default `false`; leave it off (see "Later") |

Notes before enabling:

- A blank `alertEmail` deploys **no alert rules**; set it for any trial that matters.
- While `enableNotifications=false` no job runs, but rows keep building up from status changes. The
  first enable can therefore produce a burst of `EXPIRED` warnings for old rows.
- With WhatsApp parked, `whatsapp_available` is false: nobody is asked for WhatsApp consent, and
  opting in is refused by the API. Opting out still works.
- Any `WHATSAPP` row left `PENDING` from before ends `FAILED/WHATSAPP_DISABLED` at its next claim
  and is replaced by an email row.

After a deploy with the flag on, set `NOTIFY_JOB_NAME` (output `notifyJobName`) as the GitHub
variable so `backend.yml` updates the job's image (`docs/github-setup.md`).

**Stopping sending.** Set `NOTIFICATIONS_MODE=off` on **both the `notify` job and the web app**
(`notificationsMode=off` and redeploy, or edit the variable on both). Status changes keep working,
rows wait and expire (72 h by default), and after resuming each row passes the relevance check
before it sends. Switching `enableNotifications` back to `false` removes the job, which is the
heavier option.

### Later: turning WhatsApp on (not active)

Do this only after the Meta business profile is complete. All **NOT VERIFIED — requires Azure
credentials** (and Meta ones).

1. Meta: business and number, webhook subscription to `statuses` and `messages`, the 10 templates
   approved. Spike on dev: a signed webhook POST through the Static Web App `/api` proxy keeps the
   header and raw body (if not, Meta calls the Container App address directly).
2. Key Vault secrets (names only): `whatsapp-access-token` (the Meta system-user token),
   `whatsapp-app-secret` (webhook signature), `whatsapp-verify-token` (the string given to Meta for
   the webhook handshake). They must exist before the next step.
3. Deploy with `enableWhatsApp=true`, `whatsappPhoneNumberId` and `whatsappApiVersion` (and
   optionally `whatsappDeliveryTimeoutMinutes`, default 30). This sets `WHATSAPP_ENABLED=true` and
   injects the three secrets and the `WHATSAPP_*` settings on the app and the notify job. Production
   settings then require all five `WHATSAPP_*` settings.
4. Trial in `allowlist` mode with the owner's numbers: each event on a device, a real stop and help
   reply, a provider failure reaches each alert. While `notificationsMode=off`, a WhatsApp stop
   reply still clears a doctor's opt-in (the web app sends no reply in `off`).
5. Production: the owner's decision, then `notificationsMode=live`.

After real WhatsApp use, turning it off and on again needs a decision on stale opt-ins first: while
parked, a stop reply gets a 403 and changes nothing, so a doctor still opted in goes straight back to
WhatsApp when it is switched on. Decide whether to clear or re-ask opt-ins before turning it back on.

## Deployment-time migrations (§37)

- **Dev**, `backend.yml` → `reusable-deploy-backend.yml`: push image → `az containerapp job update
  --image` + `az containerapp job start` on the **migrate** job → wait for `Succeeded` → update the
  cleanup and notify jobs → `az containerapp update --image` (new revision) → wait until the revision
  is `Healthy` → smoke test. Replicas never migrate (`entrypoint.sh web` refuses
  `RUN_MIGRATIONS_ON_START`).
- **Production**, `release-production.yml`: refuse an older release → copy the artifacts by digest →
  infrastructure, keeping the running image → **migrate job** → `release_check` → cleanup and notify
  jobs → new revision → frontend → smoke test → release record. The first deployment
  (`mode=bootstrap`) applies the schema before the web app exists (`docs/production-runbook.md`).
- `/api/ready/` fails with `schema: pending` while a migration this image knows about is unapplied, so
  a revision that outruns its migration never gets traffic. An older image on a newer schema stays ready.
- The migrate job runs `migrate --noinput` then `createcachetable` (shared rate-limit cache,
  `CACHE_URL=dbcache://django_cache`).
- While the job runs, the **previous revision keeps serving** against the migrated schema, so every
  migration must be backward compatible (expand/contract, `django-safe-migration`): add nullable
  columns / new tables first; backfill; switch code; drop old columns in a later release.
- A failed migration stops the pipeline before the app is touched. Fix forward with a new
  migration; never edit an applied one.

### Rolling back

**Production:** `mode=rollback` of `release-production.yml` re-promotes an earlier release, backend and
frontend together (`docs/production-runbook.md`, "Rolling back a release"). The commands below are the
manual fallback, and the way on dev.

```bash
# Application only (schema unchanged or still compatible): previous image as a new revision
az containerapp revision list -n "$APP" -g "$RG" \
  --query "[].{name:name, image:properties.template.containers[0].image, created:properties.createdTime}" -o table
az containerapp update -n "$APP" -g "$RG" --image <previous-image>
```

Do not reverse migrations in production as a rollback (data loss risk); because migrations are
expand/contract, the previous image works on the newer schema. If a migration damaged data, restore
the database: `docs/production-runbook.md`, "Restoring the database".

## Backups and recovery (§48)

> **Restore NOT VERIFIED.** The protection settings below are deployed on dev and checked in the
> templates by `check-template-security.py`, but no restore has been run against Azure yet. The
> first restore drill, on temporary copies with synthetic data, is part of going live
> (`docs/production-acceptance.md`, REC-1 to REC-6).

### What is protected (configured by Bicep)

| Store | Protection | dev | prod | Parameter |
|---|---|---|---|---|
| PostgreSQL | automated backups + point-in-time restore (PITR) | 7 days | 35 days | `postgresBackupRetentionDays` |
| PostgreSQL | geo-redundant backup (restore in the paired region) | off | **on** | `postgresGeoRedundantBackup` |
| PostgreSQL | zone-redundant high availability | off | off, so no automatic failover (enable when the RTO requires it; doubles compute) | `postgresHighAvailabilityMode` |
| Blob documents | soft delete for blobs **and** the container | 7 days | 14 days | `blobSoftDeleteRetentionDays` |
| Blob documents | versioning; previous versions deleted by a lifecycle rule after | 30 days | 90 days | `blobPreviousVersionRetentionDays` |
| Blob documents | redundancy | LRS | ZRS, within one region | `storageSkuName` |
| Key Vault | soft delete + **purge protection** | 7 days | 90 days | `keyVaultSoftDeleteRetentionDays` (fixed at creation) |
| Configuration | Bicep, workflows and scripts in Git; images in ACR by commit and digest; production's release records in its registry | | | |

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
| Region outage (prod) | database ≤ 1 hour (geo-backup lag); **documents are not recoverable with ZRS** | several hours: new environment in the paired region; not promised | D |

### A. Restore PostgreSQL to a point in time

PITR always creates a **new server**; the original stays untouched until you switch. **Follow
`docs/production-runbook.md`, "Restoring the database":** the recovery hold pauses writers, sending and
cleanup; `POSTGRES_SERVER_NAME_OVERRIDE` makes the selection survive every later deployment; and
reconciliation stops old notifications sending again and shows blobs that cleanup would delete.
`infrastructure/scripts/recovery.sh` runs each step, on dev or prod. Validate through the Static Web
App host: the Container App's own address answers 401.

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
# deleted OR overwritten blob. Versioning is on, so a delete turns the current blob into a
# previous version; `az storage blob undelete` does NOT bring it back (REC-2 drill, 2026-11-07).
# List the versions, then put the wanted version (the latest one, for a delete) back as current.
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

Everything except data is in Git: create a resource group (another region if needed), run
`bootstrap-production.sh` (`docs/production-runbook.md`, "Bootstrap"), and select the geo-restored or
PITR server with `POSTGRES_SERVER_NAME_OVERRIDE`. Re-run `create-entra-app` with the new public URL,
and move the domain with `cutover-domain.sh`. **Blob data has no cross-region copy with LRS or ZRS, so a
regional rebuild brings back the database but not the documents.** If the organization requires
that, the owner chooses `Standard_GZRS` (a cost decision, not configured). Do not promise whole-region
recovery until that choice is made and drilled.

### Restore drill (once per quarter, on temporary copies)

`docs/production-runbook.md`, "Restore drills": synthetic data, sending off, a temporary server and a
temporary container, and no permanent environment. Record the measured RPO and RTO there and in
`docs/progress.md`, then delete the copies.

## Production upgrade path (§34)

The default is a secure MVP, and it is what production uses (owner, D150: private networking off):
PostgreSQL accepts only Azure-internal connections (`0.0.0.0` rule) plus Entra tokens + TLS; Blob and
Key Vault have public endpoints but no anonymous/shared-key access; Azure OpenAI has keys disabled.
If that is ever revisited, `enablePrivateNetworking=true` (it cannot be changed after the server is
created, so it means a rebuild) adds a VNet with a delegated Container Apps subnet, a VNet-integrated
PostgreSQL server without public access, and private endpoints + private DNS for Blob, Key Vault
and OpenAI (their public network access disabled). Operators then need a jump host / VPN in the
VNet for `setup-postgres-entra.sh` and Key Vault secret changes; Container Registry stays public
(Basic/Standard have no private endpoints; Premium does). Further options, none chosen: Microsoft
Defender for Storage malware scanning (L8, off by owner decision), Defender for Cloud, Front Door WAF
in front of the Static Web App.

## Cost (§52)

**Current estimate for production: `docs/production-cost-estimate-2026-11-05.md`**, with retail prices
for its region, what was assumed, and the budget command.

**Cheapest reasonable dev:** the `dev.bicepparam` defaults — scale-to-zero app, B1ms, Basic ACR,
LRS, 1 GB/day log cap, no OCR, no private networking. Static Web Apps Standard is kept because the
linked backend (same-origin cookies, §4.1) requires it; the Free plan has no linked backend.

**Initial production configuration** (`prod.bicepparam`): Container App 1 vCPU / 2 GiB, 1–5
replicas, 3 Gunicorn workers; PostgreSQL General Purpose D2ds_v5, 64 GB, 35-day PITR,
geo-redundant backup, HA off; Storage ZRS; ACR Standard; Log Analytics 90 days without a daily
cap; Application Insights with Entra-only ingestion; OCR off; private networking off (D150).

### Cost drivers (PROMPT.md §52)

| Driver | What makes it grow | How to control it |
|---|---|---|
| **PostgreSQL compute** | the SKU runs 24/7 whatever the traffic; HA doubles it | Burstable for dev, General Purpose only in prod; stop an unused dev server (`az postgres flexible-server stop`); HA only when the RTO requires it |
| **PostgreSQL storage and backups** | provisioned GB (not used GB); backup storage above 100 % of the provisioned size; geo-redundant backup stores a second copy | start at 32/64 GB (storage can only grow); keep retention at what the RPO needs (7/14/35 days) |
| **Container Apps vCPU-seconds and min replicas** | `minReplicas ≥ 1` bills idle time all month; active time per vCPU-second and GiB-second; jobs per execution second | dev scales to zero (`minReplicas = 0`; the first request after idle is slow); raise `maxReplicas` for peaks rather than the minimum |
| **Static Web Apps Standard** | flat per app per month + bandwidth above 100 GB | one app per environment; Standard only because the linked backend needs it |
| **Blob storage and transactions** | stored GB (documents + previous versions + soft-deleted blobs), read/write operations; ZRS costs more than LRS | 8 MB upload cap and per-user upload limit; lifecycle rule deletes old versions; the cleanup job purges orphans |
| **Log Analytics ingestion** | GB ingested per day (requests, dependencies, logs) and retention beyond the included period | `LOG_LEVEL=INFO`, no bodies, Gunicorn access log off; daily cap in dev (`logAnalyticsDailyQuotaGb`); Application Insights sampling if traffic grows |
| **Azure OpenAI tokens per OCR call** | one image per call (image tokens dominate) + up to 1 000 output tokens; cost = calls × tokens × model price | off by default; only on the doctor's click, one call per document, 30 calls per user per hour; pick the smallest vision model that reads Arabic IDs reliably |
| **Private networking** | private endpoints (per hour + per GB), private DNS zones, VNet-integrated PostgreSQL; ACR Premium if the registry must be private too | off in dev and prod (owner, D150); pinned in `prod.bicepparam` |
| **Container Apps environment** | possible *Environment Management Hour* meter (Q-T16) | check the first month's bill |
| **Key Vault** | operations (negligible: Container Apps caches the references) | — |

**Increase as traffic grows:** `maxReplicas` and `httpConcurrency` first (seasonal peaks), then
`containerCpu/Memory` + `gunicornWorkers`; PostgreSQL `postgresSkuName` (D4ds_v5) and
`postgresHighAvailabilityMode=ZoneRedundant` when the RTO requires it; storage auto-grows.
Never trade away TLS, Entra auth, private containers or backups to save cost.

## Telemetry verification

**Verified on dev, 2026-10-11** (after the `f23b710` deploy). Application Insights data arrives in
the workspace `log-medsyn-dev-yoepoxdsywea2`: `AppRequests`, `AppTraces` and `AppDependencies`
have rows, and a `GET /api/v1/auth/me/` (401) sent at 13:44:24Z appeared in `AppRequests` about
1 s later (timestamp 13:44:25Z), tagged with the new revision's replica. There were no
`AppExceptions` after the deploy. A 30-day scan of `AppTraces`, `AppExceptions`,
`AppRequests` (URL) and `ContainerAppConsoleLogs_CL` for a standalone 14-digit run returned
**0** hits, so no unmasked national ID was found.

`/api/health/` and `/api/ready/` never appear in `AppRequests`: `HealthProbeMiddleware` answers
them before the OpenTelemetry middleware (by design, so probes don't flood telemetry). Their
database queries still show up in `AppDependencies`. To prove that a revision records requests,
send a normal request (for example `/api/v1/auth/me/`) and query for it.

**How to query under security defaults.** The workforce tenant (`448ad25b-…`) has security
defaults on, and the operator is a personal (live.com) guest. Data-plane tokens are refused with
`AADSTS530035`, which blocks `az monitor log-analytics query` (it requests an
`api.loganalytics.io` token). Log Analytics also accepts queries through **Azure Resource
Manager**, which needs only the ARM token from a normal interactive `az login`:

```bash
export MSYS_NO_PATHCONV=1                      # Git Bash only
SUB=$(az account show --query id -o tsv)
WS="/subscriptions/$SUB/resourceGroups/Medical_App/providers/Microsoft.OperationalInsights/workspaces/log-medsyn-dev-yoepoxdsywea2"
cat > query.json <<'JSON'
{"query": "AppRequests | where TimeGenerated > ago(1d) | summarize requests=count(), latest=max(TimeGenerated) by ResultCode"}
JSON
az rest --method post --url "https://management.azure.com${WS}/api/query?api-version=2020-08-01" \
  --body @query.json -o json            # response: {"Tables": [{"Columns": [...], "Rows": [...]}]}
rm query.json
```

Notes from running it: write the query to a file (`--body @file`), since inline JSON with KQL
pipes is fragile in shells; the response keys are capitalized (`Tables`, `Rows`); and naming a
summarize column `first` or `last` returned `SyntaxError` here (use `earliest` / `latest`). The
same route answers `ContainerAppConsoleLogs_CL`, which is how the migrate job's output is read
once an execution has finished (`az containerapp job logs show` only streams running replicas).

Useful checks:

```text
AppRequests | where TimeGenerated > ago(1d) | summarize count() by ResultCode, bin(TimeGenerated, 1h)
union withsource=T AppRequests, AppTraces, AppDependencies, AppExceptions | where TimeGenerated > ago(1d) | summarize rows=count(), latest=max(TimeGenerated) by T
AppExceptions | where TimeGenerated > ago(1d) | summarize count() by ProblemId
ContainerAppConsoleLogs_CL | where ContainerGroupName_s startswith "<job-execution-name>" | project TimeGenerated, Log_s
union AppTraces, AppExceptions, AppRequests, ContainerAppConsoleLogs_CL | where TimeGenerated > ago(30d) | extend text = strcat(tostring(column_ifexists('Message','')), ' ', tostring(column_ifexists('OuterMessage','')), ' ', tostring(column_ifexists('Url','')), ' ', tostring(column_ifexists('Log_s',''))) | where text matches regex @'(^|[^0-9])[0-9]{14}([^0-9]|$)' | summarize hits=count()
```

The last one must return `hits = 0`. The Azure portal's **Logs** blade (interactive MFA sign-in)
works too. CLI sessions with the guest account still expire after about an hour, and the lasting
fix is a work account in the tenant for operators.

## Retired plan identity — removed 2026-10-11

D145 dropped the pull-request what-if, and `setup-github-oidc` no longer creates the plan identity.
The leftovers of an earlier dev run were **deleted on 2026-10-11 with the owner's approval**
(Session 13), after checking that no workflow referenced a `-plan` environment:

| Deleted | Checked before | Checked after |
|---|---|---|
| GitHub environments `dev-plan` (9 variables, no rules), `staging-plan`, `prod-plan` (empty) | no `-plan` reference in `.github/workflows` | only `dev`, `staging`, `prod` remain, rules unchanged; `dev` still has its 13 variables |
| role assignments of `id-github-medsyn-dev-plan`: Reader and *Deployment What-If Operator (Medical_App)* on `Medical_App` | exactly these two, subscription-wide | none left for that principal |
| managed identity `id-github-medsyn-dev-plan` (with federated credential `github-dev-plan`, subject `…:environment:dev-plan`) | — | `ResourceNotFound`; only `id-medsyn-dev` and `id-github-medsyn-dev` remain |
| custom role *Deployment What-If Operator (Medical_App)* | assigned only to the plan identity, then to nobody | only *Deployer (Medical_App)* remains at the resource-group scope |

Runtime and deploy resources were not touched: after the cleanup the Container App revision
`--gfee502b16c13-1` was Running on image `fee502b…`, `/api/ready/` returned `database: ok`, and the
deploy identity still has its three assignments and its `environment:dev` federated credential.

If another environment ever has the same leftovers, use the ARM-only form below. Under security
defaults `--assignee` fails (it resolves the principal through Microsoft Graph). Delete the
assignments **before** the identity, or they remain orphaned.

```bash
export MSYS_NO_PATHCONV=1                 # Git Bash only
RG=<resource-group>; PLAN=id-github-medsyn-<env>-plan
ROLE="Deployment What-If Operator (<resource-group>)"
SCOPE="/subscriptions/<subscription-id>/resourceGroups/$RG"
PRINCIPAL=$(az identity show -g "$RG" -n "$PLAN" --query principalId -o tsv)
ROLE_ID=$(az role definition list --name "$ROLE" --custom-role-only true --scope "$SCOPE" --query "[0].name" -o tsv)
az role assignment list --all --fill-principal-name false \
  --query "[?principalId=='$PRINCIPAL'].{role:roleDefinitionName,id:id}" -o table      # inspect
az role assignment list --all --fill-principal-name false \
  --query "[?ends_with(roleDefinitionId,'$ROLE_ID')].principalId" -o tsv                # must be only $PRINCIPAL
gh api -X DELETE "repos/<owner>/<repo>/environments/<env>-plan"
az role assignment delete --ids $(az role assignment list --all --fill-principal-name false \
  --query "[?principalId=='$PRINCIPAL'].id" -o tsv)
az identity delete -g "$RG" -n "$PLAN"
az role definition delete --name "$ROLE" --custom-role-only true --scope "$SCOPE"   # only when unassigned
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Container App creation fails with a Key Vault reference error | Secrets missing (step 4/5) or the identity's *Key Vault Secrets User* assignment not yet propagated — wait a few minutes and redeploy. |
| Revision never becomes ready; logs show `ImproperlyConfigured` | A required setting is empty (`ENTRA_*`, secrets). Production settings refuse to start on purpose. |
| `password authentication failed for user "id-medsyn-<env>"` | Step 6 not run, wrong `AZURE_CLIENT_ID` on the app (must be the user-assigned identity's client id — the template sets it), or token for another tenant. |
| `/api/ready/` answers 503 with `schema: pending` | This image knows a migration that is not applied: the migrate job did not run, or failed. Run it (or re-run the deployment). The revision gets no traffic meanwhile, by design. |
| Revision or job fails with `CURRENT_FISCAL_YEAR must be set` | Production settings refuse to start without it. Bicep sets it from `currentFiscalYear`, so deploy the infrastructure first, then re-run the backend deploy. Never infer it from the calendar. |
| Blob `403 AuthorizationPermissionMismatch` | Role assignment still propagating, or `BLOB_ACCOUNT_URL` points at another account. Shared-key access is disabled by design. |
| SAS document links fail | *Storage Blob Delegator* missing on the account (user-delegation key). |
| CSRF failure on POST | The browser origin is not in `CSRF_TRUSTED_ORIGINS` (custom domain not set as `publicHostname`). |
| Cookies not sent / 401 after sign-in | The SPA is not served from the same origin as `/api` (linked backend missing — check `static-web-app-link`). |
| `DisallowedHost` | The Host header Django sees behind the linked backend is not in `ALLOWED_HOSTS` (Q-T13): add it via `publicHostname` or extend `allowedHosts` in `main.bicep`. |
| OCR `OCR_UNAVAILABLE` | Model deployment missing/quota exhausted (`429`), or *Cognitive Services OpenAI User* not propagated. |
