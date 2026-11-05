#!/usr/bin/env bash
# First deployment of production, up to the point where the reviewed release workflow takes over
# (docs/production-runbook.md, "Bootstrap"). Dev data and dev secrets are never copied, and
# seed_dev_data is never run.
#
# A stage only shows what it would do. Add --execute to do it, and it is safe to repeat: each stage
# looks at what exists first and never replaces a secret that is already there.
#
#   bootstrap-production.sh --env-file .env.production-bootstrap status
#   bootstrap-production.sh --env-file .env.production-bootstrap <stage> [--execute]
#
# Stages, in order. Each creates billable resources or changes trust, so each needs the owner's
# approval first:
#   preflight       (read only) tools, sign-in, GitHub protection, region support, quota
#   resource-group  the production resource group
#   github-oidc     runtime and deploy identities, federated to the GitHub environment `prod`
#   foundation      Bicep phase 1: everything except the app, its jobs and the SWA link
#   django-secret   generates django-secret-key in Key Vault if missing
#   entra           the separate production app registration, on the Static Web App default host
#   postgres        Entra administrator, database and the runtime identity's role
#   ses-secrets     (optional until the allowlist trial) SES sender keys and the allowlist
#   github          the prod variables from deployment outputs, and the ALERT_EMAIL secret
#   next            prints the command that starts the bootstrap release
#
# Requires: az, gh, psql >= 15, python, bash (Git Bash or WSL on Windows).
set -euo pipefail

export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PARAM_FILE="${REPO_ROOT}/infrastructure/parameters/prod.bicepparam"
TEMPLATE="${REPO_ROOT}/infrastructure/main.bicep"
DEPLOYMENT=main-prod
ENVIRONMENT=prod

usage() {
    sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

env_file=""
stage=""
execute=false
while [ $# -gt 0 ]; do
    case "$1" in
        --env-file) env_file="${2:?}"; shift 2 ;;
        --execute) execute=true; shift ;;
        -h | --help) usage 0 ;;
        -*) echo "Unknown option: $1" >&2; usage 2 ;;
        *) stage="$1"; shift ;;
    esac
done
[ -n "$stage" ] || usage 2
[ -n "$env_file" ] && [ -f "$env_file" ] || {
    echo "--env-file must name your filled-in copy of infrastructure/production-bootstrap.env.example" >&2
    exit 2
}
# shellcheck disable=SC1090
set -a && . "$env_file" && set +a

require() {
    local name missing=0
    for name in "$@"; do
        if [ -z "${!name:-}" ]; then
            echo "  missing input: ${name}" >&2
            missing=1
        fi
    done
    [ "$missing" = 0 ] || { echo "Fill these in ${env_file}." >&2; exit 2; }
}

# Runs the command under --execute; otherwise shows it. Arguments that hold secrets are never passed
# here: secrets go through files.
act() {
    if [ "$execute" = true ]; then
        "$@"
    else
        printf '  would run:'
        printf ' %q' "$@"
        printf '\n'
    fi
}

heading() { printf '\n== %s ==\n' "$1"; }

ensure_subscription() {
    require SUBSCRIPTION_ID WORKFORCE_TENANT_ID
    local current
    current="$(az account show --query tenantId -o tsv 2>/dev/null || true)"
    if [ "$current" != "$WORKFORCE_TENANT_ID" ]; then
        echo "Sign in to the workforce tenant first: az login --tenant <WORKFORCE_TENANT_ID>" >&2
        exit 1
    fi
    az account set --subscription "$SUBSCRIPTION_ID"
}

group_exists() { [ "$(az group exists --name "$RESOURCE_GROUP")" = "true" ]; }

output() {
    az deployment group show --resource-group "$RESOURCE_GROUP" --name "$DEPLOYMENT" \
        --query "properties.outputs.${1}.value" -o tsv 2>/dev/null || true
}

require_outputs() {
    local value
    value="$(output keyVaultName)"
    [ -n "$value" ] || { echo "Run the foundation stage first: no ${DEPLOYMENT} outputs." >&2; exit 1; }
}

secret_exists() {
    [ "$(az keyvault secret list --vault-name "$1" --query "[?name=='${2}'] | length(@)" -o tsv)" != "0" ]
}

set_secret_from_file() { # vault name file
    local vault="$1" name="$2" file="$3"
    [ -f "$file" ] || { echo "No such file for ${name}." >&2; exit 2; }
    act az keyvault secret set --vault-name "$vault" --name "$name" --file "$file" \
        --encoding utf-8 --content-type "text/plain" --output none
}

stage_preflight() {
    heading "preflight (read only)"
    local tool
    for tool in az gh psql python; do
        command -v "$tool" >/dev/null || { echo "Missing tool: ${tool}" >&2; exit 1; }
    done
    require LOCATION RESOURCE_GROUP REPOSITORY STATIC_WEB_APP_LOCATION
    ensure_subscription
    echo "Subscription and tenant: signed in as expected."

    case "$RESOURCE_GROUP" in
        Medical_App) echo "RESOURCE_GROUP is the dev group. Production must be separate." >&2; exit 1 ;;
    esac

    local reviewers protected
    protected="$(gh api "repos/${REPOSITORY}/environments/${ENVIRONMENT}" --jq '.deployment_branch_policy.protected_branches // false')"
    reviewers="$(gh api "repos/${REPOSITORY}/environments/${ENVIRONMENT}" --jq '[.protection_rules[]? | select(.type == "required_reviewers")] | length')"
    [ "$protected" = "true" ] && [ "$reviewers" != "0" ] || {
        echo "GitHub environment prod needs protected branches and required reviewers." >&2
        exit 1
    }
    echo "GitHub environment prod: protected branches only, ${reviewers} reviewer rule(s)."

    echo "PostgreSQL in ${LOCATION}:"
    az postgres flexible-server list-skus --location "$LOCATION" -o json 2>/dev/null | python -c "
import json, sys
wanted = 'Standard_D2ds_v5'
capabilities = json.load(sys.stdin)
geo = any(c.get('geoBackupSupported') == 'Enabled' for c in capabilities)
sku = any(s['name'] == wanted for c in capabilities for e in c.get('supportedServerEditions', []) for s in e.get('supportedServerSkus', []))
print(f'  {wanted}: {sku}; geo-redundant backup: {geo}')
if not (sku and geo):
    sys.exit('prod.bicepparam needs both. Change the region, or change the parameters in a reviewed commit.')
"
    echo "Static Web Apps region ${STATIC_WEB_APP_LOCATION}: $(az provider show -n Microsoft.Web \
        --query "resourceTypes[?resourceType=='staticSites'].locations | [0] | length(@)" -o tsv) regions offered."
    local namespace state
    for namespace in Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL Microsoft.KeyVault \
        Microsoft.Storage Microsoft.Web Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity; do
        state="$(az provider show -n "$namespace" --query registrationState -o tsv)"
        [ "$state" = "Registered" ] || echo "  provider ${namespace} is ${state}: az provider register -n ${namespace}"
    done
    echo "Policy assignments that may restrict the region:"
    az policy assignment list --disable-scope-strict-match --query "[].displayName" -o tsv | sed 's/^/  /'
    az bicep build-params --file "$PARAM_FILE" --stdout >/dev/null
    echo "prod.bicepparam compiles."
}

stage_resource_group() {
    heading "resource-group"
    require LOCATION RESOURCE_GROUP
    ensure_subscription
    if group_exists; then
        echo "${RESOURCE_GROUP} already exists."
        return
    fi
    act az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
        --tags application=medical-syndicates environment=prod --output none
}

stage_github_oidc() {
    heading "github-oidc"
    require RESOURCE_GROUP REPOSITORY
    ensure_subscription
    act bash "${SCRIPT_DIR}/setup-github-oidc.sh" --resource-group "$RESOURCE_GROUP" \
        --environment "$ENVIRONMENT" --repo "$REPOSITORY"
}

deployment_env() {
    export STATIC_WEB_APP_LOCATION
    export POSTGRES_ENTRA_ADMIN_OBJECT_ID POSTGRES_ENTRA_ADMIN_NAME POSTGRES_ENTRA_ADMIN_TYPE
    # The signed-in operator gets Key Vault Secrets Officer, only from this human-run phase.
    KEY_VAULT_OPERATOR_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv)"
    export KEY_VAULT_OPERATOR_OBJECT_ID
    export KEY_VAULT_OPERATOR_TYPE=User
    unset CONTAINER_IMAGE ENABLE_NOTIFICATIONS NOTIFICATIONS_MODE ALERT_EMAIL
}

stage_foundation() {
    heading "foundation (Bicep phase 1: no image, so no app, jobs or SWA link)"
    require RESOURCE_GROUP STATIC_WEB_APP_LOCATION
    ensure_subscription
    deployment_env
    group_exists || { echo "Run the resource-group stage first." >&2; exit 1; }
    if [ "$(az containerapp list -g "$RESOURCE_GROUP" --query 'length(@)' -o tsv | tr -d '\r')" != "0" ]; then
        echo "The application already exists. This stage is for the first deployment only: it ignores a" >&2
        echo "selected database and a hold. Change production through infrastructure.yml." >&2
        exit 1
    fi
    az deployment group what-if --resource-group "$RESOURCE_GROUP" --name "$DEPLOYMENT" \
        --template-file "$TEMPLATE" --parameters "$PARAM_FILE" --exclude-change-types Ignore NoChange
    act az deployment group create --resource-group "$RESOURCE_GROUP" --name "$DEPLOYMENT" \
        --template-file "$TEMPLATE" --parameters "$PARAM_FILE" --output none
}

stage_django_secret() {
    heading "django-secret"
    ensure_subscription
    require_outputs
    local vault file
    vault="$(output keyVaultName)"
    if secret_exists "$vault" django-secret-key; then
        echo "django-secret-key already exists; it is not replaced."
        return
    fi
    if [ "$execute" != true ]; then
        echo "  would generate a new value and store it as django-secret-key in ${vault}."
        return
    fi
    file="$(mktemp)"
    chmod 600 "$file"
    trap 'rm -f "$file"' RETURN
    python -c "import secrets, sys; open(sys.argv[1], 'w').write(secrets.token_urlsafe(64))" "$file"
    az keyvault secret set --vault-name "$vault" --name django-secret-key --file "$file" \
        --encoding utf-8 --content-type "text/plain" --output none
    echo "Stored django-secret-key (value not shown)."
}

stage_entra() {
    heading "entra (the production app registration)"
    require EXTERNAL_TENANT_ID USER_FLOW_ID SUBSCRIPTION_ID
    local current vault host
    # Outputs live in the workforce tenant, so read them before switching to the external tenant.
    ensure_subscription
    require_outputs
    vault="$(output keyVaultName)"
    host="$(output staticWebAppHostname)"
    echo "This stage needs both sign-ins, and the external tenant current:"
    echo "  az login --tenant <EXTERNAL_TENANT_ID> --allow-no-subscriptions"
    echo "  az account set --subscription <EXTERNAL_TENANT_ID>"
    if [ "$execute" != true ]; then
        echo "  would create medical-syndicates-prod with redirect https://${host}/api/v1/auth/callback/"
        echo "  would store entra-client-secret in ${vault}; --local is refused for prod."
        return
    fi
    az login --tenant "$EXTERNAL_TENANT_ID" --allow-no-subscriptions --output none
    az account set --subscription "$EXTERNAL_TENANT_ID"
    current="$(mktemp)"
    trap 'rm -f "$current"' RETURN
    bash "${SCRIPT_DIR}/create-entra-app.sh" --environment "$ENVIRONMENT" --tenant-id "$EXTERNAL_TENANT_ID" \
        --public-url "https://${host}" --key-vault "$vault" --subscription "$SUBSCRIPTION_ID" \
        --user-flow-id "$USER_FLOW_ID" | tee "$current"
    az account set --subscription "$SUBSCRIPTION_ID"
    echo
    echo "Next, in the external tenant (docs/entra-setup.md section 4; the app cannot prove these):"
    echo "  1. Group medical-admins-prod. Add the people who will be administrators."
    echo "  2. Conditional Access policy requiring MFA, for that group, on medical-syndicates-prod."
    echo "  3. Prove MFA with a real sign-in BEFORE grant_admin (docs/production-acceptance.md AUTH-3)."
}

stage_postgres() {
    heading "postgres"
    require RESOURCE_GROUP
    ensure_subscription
    require_outputs
    local args=(--resource-group "$RESOURCE_GROUP" --server "$(output postgresServerName)"
        --identity-name "$(output identityName)" --database "$(output postgresDatabaseName)" --allow-current-ip)
    if [ -n "${POSTGRES_ENTRA_ADMIN_OBJECT_ID:-}" ]; then
        args+=(--admin-object-id "$POSTGRES_ENTRA_ADMIN_OBJECT_ID" --admin-name "$POSTGRES_ENTRA_ADMIN_NAME"
            --admin-type "${POSTGRES_ENTRA_ADMIN_TYPE:-Group}")
    fi
    act bash "${SCRIPT_DIR}/setup-postgres-entra.sh" "${args[@]}"
}

stage_ses_secrets() {
    heading "ses-secrets (values come from files and are never printed)"
    ensure_subscription
    require_outputs
    local vault
    vault="$(output keyVaultName)"
    require AWS_ACCESS_KEY_ID_FILE AWS_SECRET_ACCESS_KEY_FILE
    set_secret_from_file "$vault" aws-access-key-id "$AWS_ACCESS_KEY_ID_FILE"
    set_secret_from_file "$vault" aws-secret-access-key "$AWS_SECRET_ACCESS_KEY_FILE"
    if [ -n "${NOTIFICATIONS_ALLOWLIST_FILE:-}" ]; then
        set_secret_from_file "$vault" notifications-allowlist "$NOTIFICATIONS_ALLOWLIST_FILE"
    fi
    echo "Before NOTIFICATIONS_MODE=allowlist: all of these must exist, then deploy the mode."
}

set_variable() { # name value (an empty value is left unset, so parameter defaults apply)
    if [ -n "$2" ]; then
        act gh variable set "$1" --env "$ENVIRONMENT" --repo "$REPOSITORY" --body "$2"
    fi
}

stage_github() {
    heading "github (prod variables from the deployment outputs; none is a secret)"
    require REPOSITORY RESOURCE_GROUP
    ensure_subscription
    require_outputs
    set_variable AZURE_RESOURCE_GROUP "$RESOURCE_GROUP"
    set_variable ACR_NAME "$(output containerRegistryName)"
    set_variable CONTAINER_APP_NAME "$(output containerAppName)"
    set_variable MIGRATE_JOB_NAME "$(output migrateJobName)"
    set_variable CLEANUP_JOB_NAME "$(output cleanupJobName)"
    set_variable STATIC_WEB_APP_NAME "$(output staticWebAppName)"
    set_variable STATIC_WEB_APP_LOCATION "${STATIC_WEB_APP_LOCATION:-}"
    set_variable POSTGRES_ENTRA_ADMIN_OBJECT_ID "${POSTGRES_ENTRA_ADMIN_OBJECT_ID:-}"
    set_variable POSTGRES_ENTRA_ADMIN_NAME "${POSTGRES_ENTRA_ADMIN_NAME:-}"
    set_variable POSTGRES_ENTRA_ADMIN_TYPE "${POSTGRES_ENTRA_ADMIN_TYPE:-}"
    set_variable SES_REGION "${SES_REGION:-}"
    set_variable SES_FROM_ADDRESS "${SES_FROM_ADDRESS:-}"
    echo "  The github-oidc stage printed AZURE_CLIENT_ID, AZURE_TENANT_ID and AZURE_SUBSCRIPTION_ID;"
    echo "  the entra stage printed ENTRA_AUTHORITY, ENTRA_TENANT_ID and ENTRA_CLIENT_ID. Set them too."
    if [ -n "${ALERT_EMAIL_FILE:-}" ]; then
        [ -f "$ALERT_EMAIL_FILE" ] || { echo "No such file for ALERT_EMAIL." >&2; exit 2; }
        if [ "$execute" = true ]; then
            gh secret set ALERT_EMAIL --env "$ENVIRONMENT" --repo "$REPOSITORY" <"$ALERT_EMAIL_FILE"
        else
            echo "  would set the prod environment secret ALERT_EMAIL from the file (value not shown)."
        fi
    else
        echo "  ALERT_EMAIL_FILE is empty: a release is refused until the secret ALERT_EMAIL exists."
    fi
}

stage_next() {
    heading "next"
    cat <<'EOF'
Everything local is done. Merge the commit to release, let dev deploy and accept it, then:

  gh workflow run release-production.yml --repo <owner>/<repo> --ref main \
    -f sha=<commit on main> -f mode=bootstrap -f dev_acceptance=<link to the acceptance record>

Approve the preview, read the what-if, then approve the deployment. It creates the migrate job and
applies the schema first; only then the app, its schedules and the Static Web App link. Then
docs/production-acceptance.md. Production is not ready until that has passed.
EOF
}

stage_status() {
    heading "status (read only; names and states, never values)"
    require RESOURCE_GROUP REPOSITORY
    ensure_subscription
    if ! group_exists; then
        echo "Resource group ${RESOURCE_GROUP}: not created."
        return
    fi
    echo "Resource group ${RESOURCE_GROUP}: exists."
    local vault app
    vault="$(output keyVaultName)"
    if [ -z "$vault" ]; then
        echo "Phase 1 deployment: not done."
        return
    fi
    echo "Phase 1 deployment: done (Key Vault ${vault})."
    echo "Key Vault secret names:"
    az keyvault secret list --vault-name "$vault" --query "[].name" -o tsv | sed 's/^/  /'
    echo "PostgreSQL entra admins: $(az postgres flexible-server microsoft-entra-admin list \
        -g "$RESOURCE_GROUP" -s "$(output postgresServerName)" --query 'length(@)' -o tsv)"
    app="$(az containerapp show -g "$RESOURCE_GROUP" -n "$(output containerAppName)" --query name -o tsv 2>/dev/null || true)"
    echo "Container App: ${app:-not created}"
    echo "GitHub prod variables set:"
    gh variable list --env "$ENVIRONMENT" --repo "$REPOSITORY" --json name --jq '.[].name' | sed 's/^/  /'
}

[ "$execute" = true ] || [ "$stage" = status ] || [ "$stage" = preflight ] || [ "$stage" = next ] ||
    echo "Showing what '${stage}' would do. Nothing changes without --execute."

case "$stage" in
    status) stage_status ;;
    preflight) stage_preflight ;;
    resource-group) stage_resource_group ;;
    github-oidc) stage_github_oidc ;;
    foundation) stage_foundation ;;
    django-secret) stage_django_secret ;;
    entra) stage_entra ;;
    postgres) stage_postgres ;;
    ses-secrets) stage_ses_secrets ;;
    github) stage_github ;;
    next) stage_next ;;
    *) echo "Unknown stage: ${stage}" >&2; usage 2 ;;
esac
