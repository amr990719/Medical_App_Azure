#!/usr/bin/env bash
# GitHub Actions → Azure with OIDC federated credentials, no stored Azure passwords
# (PROMPT.md §36, docs/github-setup.md). Run once per environment. Idempotent.
#
# Creates, in the environment's resource group:
#   * a user-assigned identity `id-github-<base>-<env>` used ONLY by GitHub Actions;
#   * a federated credential trusting tokens for `repo:<owner>/<repo>:environment:<env>`
#     (only jobs that run in that GitHub environment, with its protection rules, can use it);
#   * role assignments scoped to the resource group:
#       Contributor                                  deploy Bicep, update the Container App,
#                                                    start the migrate job, read the SWA token
#       AcrPush                                      push images to the environment's registry
#       Role Based Access Control Administrator      ONLY for the data-plane roles main.bicep
#         (condition-restricted)                     assigns (blob, delegator, Key Vault, AcrPull,
#                                                    OpenAI, metrics publisher)
#
# It prints the GitHub environment variables to set; it does NOT call GitHub.
#
# Usage:
#   infrastructure/scripts/setup-github-oidc.sh \
#     --resource-group <rg> --environment dev|staging|prod --repo <owner>/<repo> [--base-name medsyn]
set -euo pipefail

usage() {
    sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

resource_group=""
environment=""
repo=""
base_name="medsyn"

while [ $# -gt 0 ]; do
    case "$1" in
        --resource-group) resource_group="${2:?}"; shift 2 ;;
        --environment) environment="${2:?}"; shift 2 ;;
        --repo) repo="${2:?}"; shift 2 ;;
        --base-name) base_name="${2:?}"; shift 2 ;;
        -h | --help) usage 0 ;;
        *) echo "Unknown argument: $1" >&2; usage 2 ;;
    esac
done

case "$environment" in
    dev | staging | prod) ;;
    *) echo "--environment must be dev, staging or prod" >&2; exit 2 ;;
esac
[ -n "$resource_group" ] || { echo "--resource-group is required" >&2; exit 2; }
case "$repo" in
    */*) ;;
    *) echo "--repo must be <owner>/<repo>" >&2; exit 2 ;;
esac
command -v az >/dev/null || { echo "Azure CLI (az) is required" >&2; exit 1; }

identity_name="id-github-${base_name}-${environment}"
subject="repo:${repo}:environment:${environment}"
issuer="https://token.actions.githubusercontent.com"

rg_id="$(az group show -n "$resource_group" --query id -o tsv)"
subscription_id="$(az account show --query id -o tsv)"
tenant_id="$(az account show --query tenantId -o tsv)"

if ! az identity show -g "$resource_group" -n "$identity_name" --output none 2>/dev/null; then
    echo "Creating identity ${identity_name}"
    az identity create -g "$resource_group" -n "$identity_name" \
        --tags purpose=github-actions environment="$environment" --output none
fi
client_id="$(az identity show -g "$resource_group" -n "$identity_name" --query clientId -o tsv)"
principal_id="$(az identity show -g "$resource_group" -n "$identity_name" --query principalId -o tsv)"

credential_name="github-${environment}"
if az identity federated-credential show -g "$resource_group" --identity-name "$identity_name" \
    -n "$credential_name" --output none 2>/dev/null; then
    az identity federated-credential update -g "$resource_group" --identity-name "$identity_name" \
        -n "$credential_name" --issuer "$issuer" --subject "$subject" \
        --audiences api://AzureADTokenExchange --output none
else
    az identity federated-credential create -g "$resource_group" --identity-name "$identity_name" \
        -n "$credential_name" --issuer "$issuer" --subject "$subject" \
        --audiences api://AzureADTokenExchange --output none
fi
echo "Federated credential ${credential_name}: ${subject}"

assign() { # role-id description [condition]
    local role="$1" label="$2" condition="${3:-}"
    local count
    count="$(az role assignment list --assignee "$principal_id" --scope "$rg_id" --role "$role" \
        --query "length(@)" -o tsv)"
    if [ "$count" != "0" ]; then
        echo "Role already assigned: ${label}"
        return
    fi
    echo "Assigning ${label}"
    if [ -n "$condition" ]; then
        az role assignment create --assignee-object-id "$principal_id" \
            --assignee-principal-type ServicePrincipal --role "$role" --scope "$rg_id" \
            --condition "$condition" --condition-version "2.0" --output none
    else
        az role assignment create --assignee-object-id "$principal_id" \
            --assignee-principal-type ServicePrincipal --role "$role" --scope "$rg_id" --output none
    fi
}

contributor="b24988ac-6180-42a0-ab88-20f7382dd24c"
acr_push="8311e382-0749-4cb8-b61a-7f3ba6c4aaa5"
rbac_admin="f58310d9-a9f6-439a-9e8d-f62e7b41a168"
# The only roles main.bicep / role-assignments.bicep may grant.
allowed_roles="ba92f5b4-2d11-453d-a403-e96b0029c9fe, db58b8e5-c6ad-4a2a-8342-4190687cbf4a, 4633458b-17de-408a-b874-0445c86b69e6, b86a8fe4-44ce-4948-aee5-eccb2c155cd7, 7f951dda-4ed3-4680-a7ca-43fe172d538d, 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 3913510d-42f4-4e42-8a64-420c390055eb"
condition="((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${allowed_roles}})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${allowed_roles}}))"

assign "$contributor" "Contributor"
assign "$acr_push" "AcrPush"
assign "$rbac_admin" "Role Based Access Control Administrator (condition-restricted)" "$condition"

cat <<EOF

GitHub environment '${environment}' variables (Settings → Environments → ${environment} → Variables).
None of these is a secret; no Azure password or deployment token is stored in GitHub.
  gh variable set AZURE_CLIENT_ID       --env ${environment} --repo ${repo} --body ${client_id}
  gh variable set AZURE_TENANT_ID       --env ${environment} --repo ${repo} --body ${tenant_id}
  gh variable set AZURE_SUBSCRIPTION_ID --env ${environment} --repo ${repo} --body ${subscription_id}
  gh variable set AZURE_RESOURCE_GROUP  --env ${environment} --repo ${repo} --body ${resource_group}
After the first Bicep deployment, also set (values from the deployment outputs):
  ACR_NAME, CONTAINER_APP_NAME, MIGRATE_JOB_NAME, STATIC_WEB_APP_NAME,
  ENTRA_AUTHORITY, ENTRA_TENANT_ID, ENTRA_CLIENT_ID   (see docs/github-setup.md)
EOF
