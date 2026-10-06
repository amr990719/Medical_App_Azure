#!/usr/bin/env bash
# GitHub Actions → Azure with OIDC federated credentials, no stored Azure passwords
# (PROMPT.md §36, docs/github-setup.md). Run once per environment. Idempotent.
#
# Creates, in the environment's resource group, two GitHub identities with different trust:
#
#   deploy  `id-github-<base>-<env>`, federated to `repo:<owner>/<repo>:environment:<env>`.
#           Before trusting it, the script checks with `gh` (read-only) that the GitHub
#           environment <env> only accepts protected branches (and, for prod, has required
#           reviewers); it stops otherwise. Roles on the resource group:
#             Deployer (<rg>)        custom role = Contributor minus: managed-identity federated
#                                    credential writes (no taking over the app identity) and
#                                    storage account key / SAS listing
#             AcrPush                push images to the environment's registry
#             Role Based Access Control Administrator, with an ABAC condition: it may create or
#                                    delete ONLY the six data-plane role assignments main.bicep
#                                    declares, and ONLY for the app identity `id-<base>-<env>`
#   plan    `id-github-<base>-<env>-plan`, federated to `...:environment:<env>-plan`, used by
#           pull-request and what-if-only runs (code that has not been reviewed yet).
#           Roles: Reader + a custom role allowing only deployment validate/what-if.
#
# The app identity `id-<base>-<env>` is created here (Bicep then manages the same resource) so
# its principal id can be written into the condition.
# Residual trust: whoever can deploy can run code as the app identity (that is what deploying
# the app means). The boundary is the reviewed, protected `main` branch.
# It prints the GitHub environment variables to set; it does NOT change anything on GitHub.
#
# Usage:
#   infrastructure/scripts/setup-github-oidc.sh \
#     --resource-group <rg> --environment dev|staging|prod --repo <owner>/<repo> \
#     [--base-name medsyn] [--skip-github-check]
set -euo pipefail

usage() {
    sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

resource_group=""
environment=""
repo=""
base_name="medsyn"
skip_github_check=false

while [ $# -gt 0 ]; do
    case "$1" in
        --resource-group) resource_group="${2:?}"; shift 2 ;;
        --environment) environment="${2:?}"; shift 2 ;;
        --repo) repo="${2:?}"; shift 2 ;;
        --base-name) base_name="${2:?}"; shift 2 ;;
        --skip-github-check) skip_github_check=true; shift ;;
        -h | --help) usage 0 ;;
        *) echo "Unknown argument: $1" >&2; usage 2 ;;
    esac
done

case "$environment" in
    dev) env_short=dev ;;
    staging) env_short=stg ;;
    prod) env_short=prd ;;
    *) echo "--environment must be dev, staging or prod" >&2; exit 2 ;;
esac
[ -n "$resource_group" ] || { echo "--resource-group is required" >&2; exit 2; }
case "$repo" in
    */*) ;;
    *) echo "--repo must be <owner>/<repo>" >&2; exit 2 ;;
esac
command -v az >/dev/null || { echo "Azure CLI (az) is required" >&2; exit 1; }

# --- The deploy credential is only as safe as the GitHub environment's protection -----------
if [ "$skip_github_check" = true ]; then
    echo "WARNING: --skip-github-check: environment '${environment}' protection NOT verified." >&2
    echo "         Until it accepts protected branches only, any branch can deploy." >&2
else
    command -v gh >/dev/null || {
        echo "GitHub CLI (gh) is required to verify the environment protection (or --skip-github-check)" >&2
        exit 1
    }
    protected="$(gh api "repos/${repo}/environments/${environment}" \
        --jq '.deployment_branch_policy.protected_branches // false')" || {
        echo "GitHub environment '${environment}' not found in ${repo} (docs/github-setup.md §2)" >&2
        exit 1
    }
    if [ "$protected" != "true" ]; then
        echo "GitHub environment '${environment}' must allow protected branches only (docs/github-setup.md §2)" >&2
        exit 1
    fi
    if [ "$environment" = prod ]; then
        reviewers="$(gh api "repos/${repo}/environments/${environment}" \
            --jq '[.protection_rules[]? | select(.type == "required_reviewers")] | length')"
        if [ "$reviewers" = "0" ]; then
            echo "GitHub environment 'prod' must require reviewers (docs/github-setup.md §2)" >&2
            exit 1
        fi
    fi
    echo "GitHub environment '${environment}' is restricted to protected branches"
fi

issuer="https://token.actions.githubusercontent.com"
rg_id="$(az group show -n "$resource_group" --query id -o tsv)"
subscription_id="$(az account show --query id -o tsv)"
tenant_id="$(az account show --query tenantId -o tsv)"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

ensure_identity() { # name purpose → prints principal id
    local name="$1" purpose="$2"
    if ! az identity show -g "$resource_group" -n "$name" --output none 2>/dev/null; then
        echo "Creating identity ${name}" >&2
        az identity create -g "$resource_group" -n "$name" \
            --tags purpose="$purpose" environment="$environment" --output none
    fi
    az identity show -g "$resource_group" -n "$name" --query principalId -o tsv
}

ensure_federation() { # identity-name github-environment
    local identity="$1" github_env="$2"
    local name="github-${github_env}" subject="repo:${repo}:environment:${github_env}" verb=create
    if az identity federated-credential show -g "$resource_group" --identity-name "$identity" \
        -n "$name" --output none 2>/dev/null; then
        verb=update
    fi
    az identity federated-credential "$verb" -g "$resource_group" --identity-name "$identity" \
        -n "$name" --issuer "$issuer" --subject "$subject" \
        --audiences api://AzureADTokenExchange --output none
    echo "Federated credential on ${identity}: ${subject}"
}

ensure_custom_role() { # role-name definition-file (create or update, then wait for replication)
    local name="$1" file="$2" id
    id="$(az role definition list --custom-role-only true --name "$name" --query "[0].name" -o tsv)"
    if [ -z "$id" ]; then
        echo "Creating custom role ${name}"
        az role definition create --role-definition "@${file}" --output none
        for _ in 1 2 3 4 5 6; do
            [ -n "$(az role definition list --custom-role-only true --name "$name" --query "[0].name" -o tsv)" ] && break
            sleep 10
        done
    else
        echo "Updating custom role ${name}"
        # `az role definition update` finds the definition by its Name within AssignableScopes.
        az role definition update --role-definition "@${file}" --output none
    fi
}

assign() { # principal-id role label [condition]
    local principal="$1" role="$2" label="$3" condition="${4:-}"
    local existing current
    existing="$(az role assignment list --assignee "$principal" --scope "$rg_id" --role "$role" \
        --query "[0].id" -o tsv)"
    if [ -n "$existing" ]; then
        current="$(az role assignment list --assignee "$principal" --scope "$rg_id" --role "$role" \
            --query "[0].condition" -o tsv)"
        if [ "$current" = "$condition" ]; then
            echo "Role already assigned: ${label}"
            return
        fi
        echo "Replacing ${label} (condition changed)"
        az role assignment delete --ids "$existing" --output none
    fi
    echo "Assigning ${label}"
    if [ -n "$condition" ]; then
        az role assignment create --assignee-object-id "$principal" \
            --assignee-principal-type ServicePrincipal --role "$role" --scope "$rg_id" \
            --condition "$condition" --condition-version "2.0" --output none
    else
        az role assignment create --assignee-object-id "$principal" \
            --assignee-principal-type ServicePrincipal --role "$role" --scope "$rg_id" --output none
    fi
}

# --- App identity (same name as main.bicep: id-<base>-<env-short>) ---------------------------
app_identity="id-${base_name}-${env_short}"
app_principal="$(ensure_identity "$app_identity" app)"

# --- Deploy identity -------------------------------------------------------------------------
deploy_identity="id-github-${base_name}-${environment}"
deploy_principal="$(ensure_identity "$deploy_identity" github-actions-deploy)"
deploy_client="$(az identity show -g "$resource_group" -n "$deploy_identity" --query clientId -o tsv)"
ensure_federation "$deploy_identity" "$environment"

deployer_role="Deployer (${resource_group})"
cat >"${work_dir}/deployer.json" <<JSON
{
  "Name": "${deployer_role}",
  "Description": "Contributor without managed-identity federated credential writes and without storage account key/SAS listing (GitHub deploy identity).",
  "Actions": ["*"],
  "NotActions": [
    "Microsoft.Authorization/*/Delete",
    "Microsoft.Authorization/*/Write",
    "Microsoft.Authorization/elevateAccess/Action",
    "Microsoft.Blueprint/blueprintAssignments/write",
    "Microsoft.Blueprint/blueprintAssignments/delete",
    "Microsoft.Compute/galleries/share/action",
    "Microsoft.Purview/consents/write",
    "Microsoft.Purview/consents/delete",
    "Microsoft.Resources/deploymentStacks/manageDenySetting/action",
    "Microsoft.Subscription/cancel/action",
    "Microsoft.Subscription/enable/action",
    "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write",
    "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/delete",
    "Microsoft.Storage/storageAccounts/listKeys/action",
    "Microsoft.Storage/storageAccounts/regenerateKey/action",
    "Microsoft.Storage/storageAccounts/ListAccountSas/action",
    "Microsoft.Storage/storageAccounts/listServiceSas/action"
  ],
  "AssignableScopes": ["${rg_id}"]
}
JSON
ensure_custom_role "$deployer_role" "${work_dir}/deployer.json"

contributor="b24988ac-6180-42a0-ab88-20f7382dd24c"
acr_push="8311e382-0749-4cb8-b61a-7f3ba6c4aaa5"
rbac_admin="f58310d9-a9f6-439a-9e8d-f62e7b41a168"
# The six role definitions role-assignments.bicep grants to the app identity.
app_roles="ba92f5b4-2d11-453d-a403-e96b0029c9fe, db58b8e5-c6ad-4a2a-8342-4190687cbf4a, 4633458b-17de-408a-b874-0445c86b69e6, 7f951dda-4ed3-4680-a7ca-43fe172d538d, 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 3913510d-42f4-4e42-8a64-420c390055eb"
condition="((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${app_roles}} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {${app_principal}})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${app_roles}} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {${app_principal}}))"

assign "$deploy_principal" "$deployer_role" "$deployer_role"
assign "$deploy_principal" "$acr_push" "AcrPush"
assign "$deploy_principal" "$rbac_admin" \
    "Role Based Access Control Administrator (app roles, app identity only)" "$condition"

# Remove a broad Contributor assignment left by an earlier version of this script.
old_contributor="$(az role assignment list --assignee "$deploy_principal" --scope "$rg_id" \
    --role "$contributor" --query "[0].id" -o tsv)"
if [ -n "$old_contributor" ]; then
    echo "Removing the previous Contributor assignment of ${deploy_identity}"
    az role assignment delete --ids "$old_contributor" --output none
fi

# --- Plan identity (pull requests, what-if only) ----------------------------------------------
plan_identity="id-github-${base_name}-${environment}-plan"
plan_principal="$(ensure_identity "$plan_identity" github-actions-plan)"
plan_client="$(az identity show -g "$resource_group" -n "$plan_identity" --query clientId -o tsv)"
ensure_federation "$plan_identity" "${environment}-plan"

whatif_role="Deployment What-If Operator (${resource_group})"
cat >"${work_dir}/whatif.json" <<JSON
{
  "Name": "${whatif_role}",
  "Description": "Validate and preview (what-if) resource group deployments; no write access.",
  "Actions": [
    "Microsoft.Resources/deployments/read",
    "Microsoft.Resources/deployments/validate/action",
    "Microsoft.Resources/deployments/whatIf/action",
    "Microsoft.Resources/deployments/operationstatuses/read"
  ],
  "NotActions": [],
  "AssignableScopes": ["${rg_id}"]
}
JSON
ensure_custom_role "$whatif_role" "${work_dir}/whatif.json"
assign "$plan_principal" "Reader" "Reader"
assign "$plan_principal" "$whatif_role" "$whatif_role"

protection="deployment branches: protected branches only (main)"
if [ "$environment" = prod ]; then protection="${protection}; required reviewers"; fi

cat <<EOF

GitHub environments (Settings → Environments). None of these values is a secret.
  ${environment}        ${protection}
    gh variable set AZURE_CLIENT_ID       --env ${environment} --repo ${repo} --body ${deploy_client}
  ${environment}-plan   no branch restriction (pull requests); read + what-if only
    gh variable set AZURE_CLIENT_ID       --env ${environment}-plan --repo ${repo} --body ${plan_client}
  Both environments:
    gh variable set AZURE_TENANT_ID       --env <environment> --repo ${repo} --body ${tenant_id}
    gh variable set AZURE_SUBSCRIPTION_ID --env <environment> --repo ${repo} --body ${subscription_id}
    gh variable set AZURE_RESOURCE_GROUP  --env <environment> --repo ${repo} --body ${resource_group}
After the first Bicep deployment, also set (values from the deployment outputs, docs/github-setup.md):
  ACR_NAME, CONTAINER_APP_NAME, MIGRATE_JOB_NAME, CLEANUP_JOB_NAME, STATIC_WEB_APP_NAME,
  ENTRA_AUTHORITY, ENTRA_TENANT_ID, ENTRA_CLIENT_ID
EOF
