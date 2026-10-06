#!/usr/bin/env bash
# Creates or updates the Microsoft Entra External ID app registration of one environment
# (PROMPT.md §27, docs/entra-setup.md). Idempotent: re-running updates redirect URIs and keeps
# the existing client secret unless --rotate-secret is given.
#
# Django is a confidential OIDC client (BFF): web platform, authorization code flow + PKCE,
# implicit ID/access-token issuance OFF, delegated openid/profile/email only. The client secret
# never appears on screen: it goes straight into Key Vault (secret `entra-client-secret`).
#
# Prerequisites (two sign-ins, both kept in the az CLI profile):
#   az login --tenant <external-tenant-id> --allow-no-subscriptions   # app registration
#   az login --tenant <workforce-tenant-id>                           # Key Vault (subscription)
#   az account set --subscription <external-tenant-id>   # make the external tenant current
#
# Usage:
#   infrastructure/scripts/create-entra-app.sh \
#     --environment dev \
#     --tenant-id <external-tenant-id> \
#     --public-url https://<static-web-app-host> [--public-url https://<custom-domain>] \
#     [--local] \
#     [--key-vault <vault-name> --subscription <subscription-id>] \
#     [--user-flow-id <sign-up-sign-in-user-flow-id>] \
#     [--rotate-secret] [--secret-years 1]
set -euo pipefail

usage() {
    sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

environment=""
tenant_id=""
key_vault=""
subscription=""
user_flow_id=""
rotate_secret=false
secret_years=1
include_local=false
public_urls=()

while [ $# -gt 0 ]; do
    case "$1" in
        --environment) environment="${2:?}"; shift 2 ;;
        --tenant-id) tenant_id="${2:?}"; shift 2 ;;
        --public-url) public_urls+=("${2:?}"); shift 2 ;;
        --local) include_local=true; shift ;;
        --key-vault) key_vault="${2:?}"; shift 2 ;;
        --subscription) subscription="${2:?}"; shift 2 ;;
        --user-flow-id) user_flow_id="${2:?}"; shift 2 ;;
        --rotate-secret) rotate_secret=true; shift ;;
        --secret-years) secret_years="${2:?}"; shift 2 ;;
        -h | --help) usage 0 ;;
        *) echo "Unknown argument: $1" >&2; usage 2 ;;
    esac
done

case "$environment" in
    dev | staging | prod) ;;
    *) echo "--environment must be dev, staging or prod" >&2; exit 2 ;;
esac
[ -n "$tenant_id" ] || { echo "--tenant-id is required" >&2; exit 2; }
[ "${#public_urls[@]}" -gt 0 ] || { echo "at least one --public-url is required" >&2; exit 2; }
if [ -n "$key_vault" ] && [ -z "$subscription" ]; then
    echo "--key-vault needs --subscription (the vault lives in the workforce tenant)" >&2
    exit 2
fi
if [ "$environment" = "prod" ] && [ "$include_local" = true ]; then
    echo "--local is refused for prod (no localhost redirect URIs in production)" >&2
    exit 2
fi
command -v az >/dev/null || { echo "Azure CLI (az) is required" >&2; exit 1; }

current_tenant="$(az account show --query tenantId -o tsv)"
if [ "$current_tenant" != "$tenant_id" ]; then
    echo "The current az account is in tenant $current_tenant, not $tenant_id." >&2
    echo "Run: az login --tenant $tenant_id --allow-no-subscriptions && az account set --subscription $tenant_id" >&2
    exit 1
fi

display_name="medical-syndicates-${environment}"

# Redirect URIs: the BFF callback and the post-logout page (Entra only redirects after sign-out
# to a registered reply URL).
redirect_uris=()
for url in "${public_urls[@]}"; do
    url="${url%/}"
    case "$url" in
        https://*) ;;
        *) echo "--public-url must use https: $url" >&2; exit 2 ;;
    esac
    redirect_uris+=("${url}/api/v1/auth/callback/" "${url}/signed-out")
done
if [ "$include_local" = true ]; then
    redirect_uris+=("http://localhost:5173/api/v1/auth/callback/" "http://localhost:5173/signed-out")
fi

app_id="$(az ad app list --display-name "$display_name" --query "[0].appId" -o tsv)"
if [ -z "$app_id" ]; then
    echo "Creating app registration $display_name"
    app_id="$(az ad app create \
        --display-name "$display_name" \
        --sign-in-audience AzureADMyOrg \
        --enable-id-token-issuance false \
        --enable-access-token-issuance false \
        --query appId -o tsv)"
else
    echo "Updating existing app registration $display_name"
fi

# Merge with the URIs already registered (another script run may have added a custom domain).
existing_uris="$(az ad app show --id "$app_id" --query "web.redirectUris" -o tsv)"
merged_uris=()
while IFS= read -r uri; do
    if [ -n "$uri" ]; then merged_uris+=("$uri"); fi
done < <(printf '%s\n' "${redirect_uris[@]}" "$existing_uris" | tr -d '\r' | sort -u)
az ad app update --id "$app_id" \
    --web-redirect-uris "${merged_uris[@]}" \
    --enable-id-token-issuance false \
    --enable-access-token-issuance false \
    --sign-in-audience AzureADMyOrg

# The `email` claim in the ID token (Q-T7); users are still mapped by oid + tid only.
claims_file="$(mktemp)"
trap 'rm -f "$claims_file"' EXIT
cat >"$claims_file" <<'JSON'
{"idToken": [{"name": "email", "essential": false}]}
JSON
az ad app update --id "$app_id" --optional-claims "@${claims_file}"

# Delegated Microsoft Graph permissions: openid, profile, email (nothing else).
graph="00000003-0000-0000-c000-000000000000"
az ad app permission add --id "$app_id" --api "$graph" --api-permissions \
    "37f7f235-527c-4136-accd-4a02d197296e=Scope" \
    "14dad69e-099b-42c9-810b-d002981feec1=Scope" \
    "64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0=Scope" \
    --only-show-errors >/dev/null

if [ -z "$(az ad sp list --filter "appId eq '$app_id'" --query "[0].id" -o tsv)" ]; then
    az ad sp create --id "$app_id" --only-show-errors >/dev/null
fi
az ad app permission admin-consent --id "$app_id"

if [ -n "$user_flow_id" ]; then
    # Associate the app with the sign-up/sign-in user flow (Arabic language enabled there).
    linked="$(az rest --method GET \
        --url "https://graph.microsoft.com/v1.0/identity/authenticationEventsFlows/${user_flow_id}/conditions/applications/includeApplications" \
        --query "value[?appId=='${app_id}'] | length(@)" -o tsv)"
    if [ "$linked" = "0" ]; then
        az rest --method POST \
            --url "https://graph.microsoft.com/v1.0/identity/authenticationEventsFlows/${user_flow_id}/conditions/applications/includeApplications" \
            --headers "Content-Type=application/json" \
            --body "{\"@odata.type\": \"#microsoft.graph.authenticationConditionApplication\", \"appId\": \"${app_id}\"}" \
            --only-show-errors >/dev/null
        echo "Linked the app to user flow ${user_flow_id}"
    fi
fi

if [ -n "$key_vault" ]; then
    secret_exists="$(az keyvault secret list --vault-name "$key_vault" --subscription "$subscription" \
        --query "[?name=='entra-client-secret'] | length(@)" -o tsv)"
    if [ "$secret_exists" = "0" ] || [ "$rotate_secret" = true ]; then
        secret_file="$(mktemp)"
        chmod 600 "$secret_file"
        trap 'rm -f "$claims_file" "$secret_file"' EXIT
        # --append keeps the previous secret valid until the new revision is live; remove it
        # afterwards with `az ad app credential delete` (docs/entra-setup.md, rotation).
        az ad app credential reset --id "$app_id" --append \
            --display-name "key-vault-$(date -u +%Y%m%d)" --years "$secret_years" \
            --query password -o tsv >"$secret_file"
        expires="$(date -u -d "+${secret_years} year" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null ||
            date -u -v "+${secret_years}y" +%Y-%m-%dT%H:%M:%SZ)"
        az keyvault secret set --vault-name "$key_vault" --subscription "$subscription" \
            --name entra-client-secret --file "$secret_file" --encoding utf-8 \
            --content-type "text/plain" --expires "$expires" --output none
        rm -f "$secret_file"
        echo "Stored a new client secret in Key Vault $key_vault (entra-client-secret, expires $expires)"
    else
        echo "Key Vault $key_vault already holds entra-client-secret (use --rotate-secret to replace it)"
    fi
else
    echo "No --key-vault given: no client secret created. Re-run with --key-vault/--subscription."
fi

tenant_subdomain="$(az rest --method GET --url "https://graph.microsoft.com/v1.0/domains" \
    --query "value[?isInitial].id | [0]" -o tsv | sed 's/\.onmicrosoft\.com$//')"

cat <<EOF

Values for the ${environment} environment (GitHub environment variables / parameter env vars):
  ENTRA_TENANT_ID=${tenant_id}
  ENTRA_CLIENT_ID=${app_id}
  ENTRA_AUTHORITY=https://${tenant_subdomain}.ciamlogin.com/${tenant_id}
Registered redirect URIs:
$(printf '  %s\n' "${merged_uris[@]}")
EOF
