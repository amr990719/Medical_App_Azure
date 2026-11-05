#!/usr/bin/env bash
# Moves neqabacare.com from dev to production, with dev kept at its own hostname
# (docs/production-runbook.md, "Domain cutover", which is the order and the reasons).
# A step only shows what it would do. Add --execute to do it. DNS is in Cloudflare and is changed
# by a person; a step prints exactly which record, and leaves SES and mail records alone.
#
#   cutover-domain.sh --repo <owner>/<repo> --dev-group <rg> --prod-group <rg> <step> [--execute]
#
#   preflight        (read only) payment text, acceptance record, both sites, DNS slices
#   prepare-dev      dev.neqabacare.com on dev, with dev's Entra URIs; dev keeps the apex for now
#   prepare-prod     adds the final URLs to the production Entra app (no effect on users yet)
#   move-dev         dev's PUBLIC_HOSTNAME -> dev.neqabacare.com, redeploy dev
#   detach-dev       removes neqabacare.com from dev's Static Web App. The outage, if any, starts here
#   attach-prod      binds neqabacare.com on production and prints the DNS records to set
#   switch-prod      production's PUBLIC_HOSTNAME -> neqabacare.com, redeploy production
#   verify           the smoke check on the final host, with the old host's redirect
#   rollback         puts everything back on dev; run while `verify` or a real sign-in fails
#
# Needs: az, gh, python, curl, and for Entra steps the external tenant sign-in.
set -euo pipefail

export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FINAL_HOST="neqabacare.com"
DEV_HOST="dev.neqabacare.com"

repo=""
dev_group=""
prod_group=""
step=""
execute=false
entra_tenant="${EXTERNAL_TENANT_ID:-}"
subscription="${SUBSCRIPTION_ID:-}"
while [ $# -gt 0 ]; do
    case "$1" in
        --repo) repo="${2:?}"; shift 2 ;;
        --dev-group) dev_group="${2:?}"; shift 2 ;;
        --prod-group) prod_group="${2:?}"; shift 2 ;;
        --entra-tenant) entra_tenant="${2:?}"; shift 2 ;;
        --subscription) subscription="${2:?}"; shift 2 ;;
        --execute) execute=true; shift ;;
        -h | --help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "Unknown option: $1" >&2; exit 2 ;;
        *) step="$1"; shift ;;
    esac
done
[ -n "$repo" ] && [ -n "$dev_group" ] && [ -n "$prod_group" ] && [ -n "$step" ] || {
    echo "--repo, --dev-group, --prod-group and a step are required (--help)" >&2
    exit 2
}
[ "$dev_group" != "$prod_group" ] || { echo "dev and production must be different groups" >&2; exit 2; }

act() {
    if [ "$execute" = true ]; then
        "$@"
    else
        printf '  would run:'
        printf ' %q' "$@"
        printf '\n'
    fi
}

site_of() { az staticwebapp list -g "$1" --query "[0].name" -o tsv; }
default_host_of() { az staticwebapp show -n "$(site_of "$1")" -g "$1" --query defaultHostname -o tsv; }
slice_of() { printf '%s' "$1" | sed -E 's/^[^.]+\.([0-9]+)\.azurestaticapps\.net$/\1/'; }

deploy() { # environment
    act gh workflow run infrastructure.yml --repo "$repo" --ref main -f environment="$1" -f what_if_only=false
    echo "Wait for that run to succeed (production waits for its reviewer) before the next step."
}

add_entra_urls() { # environment url
    [ -n "$entra_tenant" ] && [ -n "$subscription" ] || {
        echo "--entra-tenant and --subscription are required for Entra steps" >&2
        exit 2
    }
    echo "This needs both sign-ins already made: az login --tenant <workforce-id>, and"
    echo "az login --tenant <external-id> --allow-no-subscriptions"
    # create-entra-app.sh insists the external tenant is current; everything else here needs the
    # subscription. Existing URIs are kept, so the old host goes on working during the move.
    act az account set --subscription "$entra_tenant"
    act bash "${SCRIPT_DIR}/create-entra-app.sh" --environment "$1" --tenant-id "$entra_tenant" \
        --public-url "$2"
    act az account set --subscription "$subscription"
}

# A rollback may run after a partial attempt: what is already gone must not stop the rest.
remove_hostname() { # resource-group hostname
    local site present
    site="$(site_of "$1")"
    present="$(az staticwebapp hostname list -n "$site" -g "$1" \
        --query "[?domainName=='$2'] | length(@)" -o tsv | tr -d '\r')"
    if [ "$present" = "0" ]; then
        echo "$2 is not bound to ${site}."
        return 0
    fi
    act az staticwebapp hostname delete -n "$site" -g "$1" --hostname "$2" --yes
}

# `gh variable delete` has no --yes, and fails when the variable is absent.
unset_variable() { # environment name
    if gh variable list --env "$1" --repo "$repo" --json name --jq '.[].name' | tr -d '\r' | grep -qx "$2"; then
        act gh variable delete "$2" --env "$1" --repo "$repo"
    else
        echo "$2 is not set on $1."
    fi
}

[ "$execute" = true ] || [ "$step" = preflight ] || [ "$step" = verify ] ||
    echo "Showing what '${step}' would do. Nothing changes without --execute."

case "$step" in
    preflight)
        problems=0
        if grep -q "PLACEHOLDER (D81" "${REPO_ROOT}/frontend/src/i18n/ar.ts"; then
            echo "NOT READY: the payment instructions are still the placeholder (frontend/src/i18n/ar.ts)."
            problems=1
        fi
        if ! python "${SCRIPT_DIR}/acceptance_record.py" "${REPO_ROOT}/docs/production-acceptance.md" \
            --stage before-cutover; then
            echo "NOT READY: docs/production-acceptance.md has items open before cutover."
            problems=1
        fi
        prod_host="$(default_host_of "$prod_group")"
        dev_site_host="$(default_host_of "$dev_group")"
        curl -fsS -o /dev/null "https://${prod_host}/api/ready/" || {
            echo "NOT READY: production does not answer on https://${prod_host}/api/ready/"
            problems=1
        }
        echo "Dev site ${dev_site_host}, production site ${prod_host}."
        if [ "$(slice_of "$prod_host")" = "$(slice_of "$dev_site_host")" ]; then
            echo "Same Static Web Apps slice: Azure refuses one domain on both, so detach-dev to"
            echo "attach-prod is a real outage of several minutes to plan for."
        else
            echo "Different slices: Microsoft's TXT validation may allow the new binding before traffic"
            echo "moves. Not verified here: plan for the outage and be pleasantly surprised."
        fi
        echo "Apex today: $(az staticwebapp hostname list -n "$(site_of "$dev_group")" -g "$dev_group" \
            --query "[].{d:domainName,s:status}" -o tsv | tr '\n' ' ')"
        [ "$problems" = 0 ] || exit 1
        echo "Preflight passed."
        ;;
    prepare-dev)
        cat <<EOF
In Cloudflare, add, DNS only:
  CNAME dev -> $(default_host_of "$dev_group")
Then re-run this step with --execute to bind it.
EOF
        act az staticwebapp hostname set -n "$(site_of "$dev_group")" -g "$dev_group" \
            --hostname "$DEV_HOST" --validation-method cname-delegation
        add_entra_urls dev "https://${DEV_HOST}"
        ;;
    prepare-prod)
        add_entra_urls prod "https://${FINAL_HOST}"
        ;;
    move-dev)
        act gh variable set PUBLIC_HOSTNAME --env dev --repo "$repo" --body "$DEV_HOST"
        deploy dev
        echo "Dev notification links now use ${DEV_HOST}. The dev allowlist is unchanged."
        ;;
    detach-dev)
        echo "The outage window, if the two sites share a slice, starts now."
        remove_hostname "$dev_group" "$FINAL_HOST"
        remove_hostname "$dev_group" "www.${FINAL_HOST}"
        ;;
    attach-prod)
        prod_host="$(default_host_of "$prod_group")"
        act az staticwebapp hostname set -n "$(site_of "$prod_group")" -g "$prod_group" \
            --hostname "$FINAL_HOST" --validation-method dns-txt-token --no-wait
        if [ "$execute" = true ]; then
            token="$(az staticwebapp hostname show -n "$(site_of "$prod_group")" -g "$prod_group" \
                --hostname "$FINAL_HOST" --query validationToken -o tsv)"
        else
            token="<shown when run with --execute>"
        fi
        cat <<EOF

In Cloudflare, change only these records:
  TXT   _dnsauth   ${token}     (and the apex validation TXT, if one holds the old token)
  CNAME @          ${prod_host}     DNS only, as D185 explains
  CNAME www        ${prod_host}     stays proxied: the Single Redirect answers it, and the origin is never used

Do not touch the SES records (DKIM CNAMEs, custom MAIL FROM, SPF, DMARC) or the mail routing of
notifications@. Check any apex TXT line by line: one of them holds SPF.

Wait until this says Ready, then run switch-prod:
  az staticwebapp hostname show -n $(site_of "$prod_group") -g ${prod_group} --hostname ${FINAL_HOST} --query status -o tsv
EOF
        ;;
    switch-prod)
        status="$(az staticwebapp hostname show -n "$(site_of "$prod_group")" -g "$prod_group" \
            --hostname "$FINAL_HOST" --query status -o tsv 2>/dev/null || true)"
        [ "$status" = "Ready" ] || {
            echo "Refused: ${FINAL_HOST} on production is '${status:-absent}', not Ready." >&2
            exit 1
        }
        act gh variable set PUBLIC_HOSTNAME --env prod --repo "$repo" --body "$FINAL_HOST"
        deploy prod
        cat <<EOF
This sets ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, the Entra redirect and logout URLs and the
notification links together. Then, in the Azure portal (Microsoft documents no CLI for it):
  Static Web App -> Custom domains -> ${FINAL_HOST} -> Set default
It makes the default host redirect here, so a sign-in cannot start on the wrong origin (Q-T24).
EOF
        ;;
    verify)
        prod_host="$(default_host_of "$prod_group")"
        client_id="$(gh variable list --env prod --repo "$repo" --json name,value \
            --jq '.[] | select(.name == "ENTRA_CLIENT_ID") | .value')"
        python "${SCRIPT_DIR}/acceptance_smoke.py" --base-url "https://${FINAL_HOST}" \
            --expect-client-id "$client_id" --redirect-from "https://${prod_host}"
        echo "Next, by hand: sign in, change something (a CSRF-protected POST), sign out, on ${FINAL_HOST}."
        echo "Record them in docs/production-acceptance.md (CUT-1 to CUT-4)."
        ;;
    rollback)
        cat <<EOF
Rolling back to dev serving ${FINAL_HOST}. Production keeps its data; sign-ins there stop.
1. Production gives the name back, and goes back to its own host:
EOF
        remove_hostname "$prod_group" "$FINAL_HOST"
        unset_variable prod PUBLIC_HOSTNAME
        deploy prod
        cat <<EOF

2. In Cloudflare: CNAME @ and CNAME www -> $(default_host_of "$dev_group"), and restore the old TXT
   tokens. Nothing else changes.
3. Dev takes the name back:
EOF
        act az staticwebapp hostname set -n "$(site_of "$dev_group")" -g "$dev_group" \
            --hostname "$FINAL_HOST" --validation-method dns-txt-token --no-wait
        act gh variable set PUBLIC_HOSTNAME --env dev --repo "$repo" --body "$FINAL_HOST"
        deploy dev
        echo "4. Any session made on the other site is gone: cookies are per host, and users sign in again."
        ;;
    *)
        echo "Unknown step: ${step} (--help)" >&2
        exit 2
        ;;
esac
