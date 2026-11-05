#!/usr/bin/env bash
# One-off management command as an execution of the migrate job (docs/production-runbook.md).
# `az containerapp exec` needs an interactive terminal, so this replaces only the container's
# arguments; the image, environment and secret references stay those of the job. The migrate job
# has no notification settings, so nothing it runs can send. Output goes to Log Analytics.
#
# Usage:
#   infrastructure/scripts/run-job-command.sh --job <migrate-job> --resource-group <rg> \
#     -- python manage.py release_check --require-admin
#
# Exits non-zero when the execution does not end Succeeded.
set -euo pipefail

export MSYS_NO_PATHCONV=1 # Git Bash must not rewrite /subscriptions/... into a Windows path

# Git Bash paths mean nothing to `az`, a Windows program. On Linux this changes nothing.
native_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$1"
    else
        printf '%s' "$1"
    fi
}

job=""
resource_group=""
while [ $# -gt 0 ]; do
    case "$1" in
        --job) job="${2:?}"; shift 2 ;;
        --resource-group) resource_group="${2:?}"; shift 2 ;;
        --) shift; break ;;
        -h | --help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [ -z "$job" ] || [ -z "$resource_group" ] || [ $# -eq 0 ]; then
    echo "--job, --resource-group and a command after -- are required" >&2
    exit 2
fi

python="$(command -v python3 >/dev/null 2>&1 && echo python3 || echo python)"
api="api-version=2025-01-01"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

job_id="$(az containerapp job show -n "$job" -g "$resource_group" --query id -o tsv)"
az rest --method get --url "https://management.azure.com${job_id}?${api}" \
    --query "{containers: properties.template.containers}" -o json >"${work}/start.json"
"$python" - "$(native_path "${work}/start.json")" "$@" <<'PY'
import json, sys
path, *command = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    body = json.load(handle)
body["containers"][0]["args"] = command
with open(path, "w", encoding="utf-8") as handle:
    json.dump(body, handle)
PY
execution="$(az rest --method post --url "https://management.azure.com${job_id}/start?${api}" \
    --body "@$(native_path "${work}/start.json")" --query name -o tsv)"
echo "Started ${execution}: $*"

deadline=$((SECONDS + 1800))
while :; do
    status="$(az containerapp job execution show -n "$job" -g "$resource_group" \
        --job-execution-name "$execution" --query properties.status -o tsv)"
    case "$status" in
        Succeeded) echo "${execution}: Succeeded"; exit 0 ;;
        Failed | Stopped | Degraded)
            echo "::error::${execution} ended ${status}. Logs: Log Analytics, ContainerAppConsoleLogs_CL where ContainerGroupName_s startswith '${execution}'" >&2
            exit 1 ;;
    esac
    if [ "$SECONDS" -ge "$deadline" ]; then
        echo "::error::${execution} is still '${status}' after 30 minutes" >&2
        exit 1
    fi
    sleep 15
done
