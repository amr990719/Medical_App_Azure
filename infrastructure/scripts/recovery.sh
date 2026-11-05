#!/usr/bin/env bash
# Database and document recovery for one environment (docs/production-runbook.md, "Recovery").
# The hold and the restored server are GitHub variables that the parameter files read, so every
# later deployment keeps them: nothing here depends on someone remembering a manual change.
#
# A step only shows what it would do. Add --execute to do it.
#
#   recovery.sh --environment <dev|prod> --repo <owner>/<repo> --resource-group <rg> <step> [--execute]
#
#   status                     hold, active server, ingress, schedules, notifications mode
#   hold-on                    RECOVERY_HOLD=true, then deploy: ingress closed, schedules moved,
#                              notifications off (the deploy runs in infrastructure.yml)
#   restore-db --restored-name <name> --restore-time <ISO8601 UTC>
#                              point-in-time restore to a NEW server; the original is untouched
#   prepare-db --restored-name <name>
#                              Entra administrator, identity role and grants on the new server
#   select-db --restored-name <name>
#                              POSTGRES_SERVER_NAME_OVERRIDE=<name>, then deploy. Survives later runs
#   migrate --restored-name <name>
#                              only if the restore point predates a migration the running image needs
#   reconcile --restored-name <name> --restore-time <ISO8601 UTC> [--apply]
#                              document report, then notifications; refuses unless the hold is in
#                              force, nothing is running, and the jobs really use that server
#   check                      release_check on the selected database, without opening anything
#   hold-off                   RECOVERY_HOLD=false, then deploy: service back, on the selected server
#
# The original server is deleted only by a person, after the restored data is accepted.
set -euo pipefail

export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOLD_CRON="0 0 1 1 *" # recoveryHoldCron in main.bicep

environment=""
repo=""
resource_group=""
step=""
execute=false
apply=false
restored_name=""
restore_time=""
while [ $# -gt 0 ]; do
    case "$1" in
        --environment) environment="${2:?}"; shift 2 ;;
        --repo) repo="${2:?}"; shift 2 ;;
        --resource-group) resource_group="${2:?}"; shift 2 ;;
        --restored-name) restored_name="${2:?}"; shift 2 ;;
        --restore-time) restore_time="${2:?}"; shift 2 ;;
        --execute) execute=true; shift ;;
        --apply) apply=true; shift ;;
        -h | --help) sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "Unknown option: $1" >&2; exit 2 ;;
        *) step="$1"; shift ;;
    esac
done
case "$environment" in
    dev | prod) ;;
    *) echo "--environment must be dev or prod" >&2; exit 2 ;;
esac
[ -n "$repo" ] && [ -n "$resource_group" ] && [ -n "$step" ] || {
    echo "--repo, --resource-group and a step are required (--help)" >&2
    exit 2
}

act() {
    if [ "$execute" = true ]; then
        "$@"
    else
        printf '  would run:'
        printf ' %q' "$@"
        printf '\n'
    fi
}

deploy_infrastructure() {
    act gh workflow run infrastructure.yml --repo "$repo" --ref main \
        -f environment="$environment" -f what_if_only=false
    echo "Approve it in GitHub if ${environment} requires a reviewer, and WAIT until it succeeds:"
    echo "the following steps check its effect and refuse if it has not happened."
}

# One read of the environment's variables. A failed read stops the script: an empty answer here
# must never be mistaken for "not set".
variables_json="$(gh variable list --env "$environment" --repo "$repo" --json name,value)"
variable() {
    python_bin="$(command -v python3 >/dev/null 2>&1 && echo python3 || echo python)"
    printf '%s' "$variables_json" | "$python_bin" -c '
import json, sys
print(next((v["value"] for v in json.load(sys.stdin) if v["name"] == sys.argv[1]), ""))' "$1" | tr -d '\r'
}

set_variable() {
    act gh variable set "$1" --env "$environment" --repo "$repo" --body "$2"
}

# Real names, from the variables a release uses. Not from the last deployment's outputs: a failed
# deployment has none, and a failed deployment is exactly when this script is needed.
app="$(variable CONTAINER_APP_NAME)"
migrate="$(variable MIGRATE_JOB_NAME)"
cleanup="$(variable CLEANUP_JOB_NAME)"
notify="$(variable NOTIFY_JOB_NAME)"
for required in app migrate cleanup; do
    [ -n "${!required}" ] || {
        echo "Refused: the GitHub environment ${environment} has no name for the ${required} resource (docs/production-runbook.md, inventory)." >&2
        exit 1
    }
done

job_env() { # job name
    az containerapp job show -n "$1" -g "$resource_group" \
        --query "properties.template.containers[0].env[?name=='$2'].value | [0]" -o tsv | tr -d '\r'
}

job_cron() {
    az containerapp job show -n "$1" -g "$resource_group" \
        --query "properties.configuration.scheduleTriggerConfig.cronExpression" -o tsv | tr -d '\r'
}

running_executions() {
    az containerapp job execution list -n "$1" -g "$resource_group" \
        --query "[?properties.status=='Running'].name" -o tsv | tr -d '\r'
}

# The server the jobs really use now, read from the migrate job's own settings.
database_host() {
    job_env "$migrate" DATABASE_URL | sed -E 's#.*@([^:/]+).*#\1#'
}

require_hold() {
    [ "$(variable RECOVERY_HOLD)" = "true" ] || {
        echo "Refused: ${step} needs the hold on (RECOVERY_HOLD=true). Run hold-on first." >&2
        exit 1
    }
}

# select-db only queues a deployment, which may be waiting for approval or may have failed. So check
# the job itself: marking the original server's live outbox as superseded could not be undone.
require_selected() {
    need --restored-name "$restored_name"
    require_hold
    local override host
    override="$(variable POSTGRES_SERVER_NAME_OVERRIDE)"
    host="$(database_host)"
    if [ "$override" != "$restored_name" ]; then
        echo "Refused: POSTGRES_SERVER_NAME_OVERRIDE is '${override}', not '${restored_name}'. Run select-db first." >&2
        exit 1
    fi
    if [ "${host%%.*}" != "$restored_name" ]; then
        echo "Refused: the migrate job still uses '${host}', not '${restored_name}'. Wait for the select-db deployment to succeed." >&2
        exit 1
    fi
    echo "The jobs use ${restored_name}."
}

require_not_running() { # job
    local running
    running="$(running_executions "$1")"
    if [ -n "$running" ]; then
        echo "Refused: ${1} is still running (${running}). The hold moved its schedule but cannot stop a run in progress. Wait, or stop it:" >&2
        echo "  az containerapp job stop -n ${1} -g ${resource_group} --job-execution-name ${running}" >&2
        exit 1
    fi
}

# The migrate job carries no notification settings, so the command cannot see this for itself.
require_sending_paused() {
    local mode cron
    if [ -n "$notify" ]; then
        cron="$(job_cron "$notify")"
        mode="$(job_env "$notify" NOTIFICATIONS_MODE)"
        if [ "$cron" != "$HOLD_CRON" ] || { [ -n "$mode" ] && [ "$mode" != off ]; }; then
            echo "Refused: the notify job has cron '${cron}' and mode '${mode:-unset}'. Wait for the hold-on deployment to succeed." >&2
            exit 1
        fi
        require_not_running "$notify"
    fi
    if [ "$(job_cron "$cleanup")" != "$HOLD_CRON" ]; then
        echo "Refused: the cleanup job is still scheduled. Wait for the hold-on deployment to succeed." >&2
        exit 1
    fi
    require_not_running "$cleanup"
    echo "Sending and cleanup are paused, and nothing is running."
}

run_in_job() {
    act bash "${SCRIPT_DIR}/run-job-command.sh" --job "$migrate" --resource-group "$resource_group" -- "$@"
}

need() {
    local name="$1" value="$2"
    [ -n "$value" ] || { echo "${name} is required for ${step}" >&2; exit 2; }
}

[ "$execute" = true ] || [ "$step" = status ] || echo "Showing what '${step}' would do. Nothing changes without --execute."

case "$step" in
    status)
        echo "RECOVERY_HOLD:                 $(variable RECOVERY_HOLD)"
        echo "POSTGRES_SERVER_NAME_OVERRIDE: $(variable POSTGRES_SERVER_NAME_OVERRIDE)"
        echo "Jobs' database host:           $(database_host)"
        echo "Ingress restrictions:          $(az containerapp show -n "$app" -g "$resource_group" \
            --query "properties.configuration.ingress.ipSecurityRestrictions[].name" -o tsv | tr '\n' ' ')"
        echo "Cleanup cron:                  $(job_cron "$cleanup")"
        echo "Cleanup running:               $(running_executions "$cleanup")"
        if [ -n "$notify" ]; then
            echo "Notify cron:                   $(job_cron "$notify")"
            echo "Notify mode:                   $(job_env "$notify" NOTIFICATIONS_MODE)"
            echo "Notify running:                $(running_executions "$notify")"
        else
            echo "Notify job:                    none known (NOTIFY_JOB_NAME is not set)"
        fi
        ;;
    hold-on)
        echo "Closes the app and stops both schedules. Users see the service unavailable until hold-off."
        set_variable RECOVERY_HOLD true
        deploy_infrastructure
        ;;
    restore-db)
        need --restored-name "$restored_name"
        need --restore-time "$restore_time"
        host="$(database_host)"
        source_server="${host%%.*}"
        # The CLI's default is Disabled, the parameter file declares what the source has, and it can
        # be set only when a server is created.
        geo="$(az postgres flexible-server show -g "$resource_group" -n "$source_server" \
            --query backup.geoRedundantBackup -o tsv | tr -d '\r')"
        echo "Restoring ${source_server} as of ${restore_time} to the new server ${restored_name}."
        echo "Billed like the original until it is deleted."
        act az postgres flexible-server restore --resource-group "$resource_group" --name "$restored_name" \
            --source-server "$source_server" --restore-time "$restore_time" --geo-redundant-backup "$geo"
        ;;
    prepare-db)
        need --restored-name "$restored_name"
        url="$(job_env "$migrate" DATABASE_URL)"
        identity="$(printf '%s' "$url" | sed -E 's#^[a-z]+://([^@]+)@.*#\1#')"
        database="$(printf '%s' "$url" | sed -E 's#.*/([^/?]+).*#\1#')"
        act bash "${SCRIPT_DIR}/setup-postgres-entra.sh" --resource-group "$resource_group" \
            --server "$restored_name" --identity-name "$identity" --database "$database" --allow-current-ip
        echo "Firewall rules are not copied by a restore. The next deployment recreates them once the"
        echo "server is selected. Confirm the what-if of that deployment changes settings, not data."
        ;;
    select-db)
        need --restored-name "$restored_name"
        require_hold
        set_variable POSTGRES_SERVER_NAME_OVERRIDE "$restored_name"
        deploy_infrastructure
        ;;
    migrate)
        require_selected
        echo "The restored database predates a migration the running image needs. Applying it."
        echo "If that migration's release caused the damage, roll back the application instead"
        echo "(mode=rollback works during a hold), and only then run reconcile."
        run_in_job migrate
        ;;
    reconcile)
        need --restore-time "$restore_time"
        require_selected
        require_sending_paused
        echo "Documents (read only): rows without bytes stop the reconciliation here."
        run_in_job python manage.py reconcile_documents --restored-to "$restore_time"
        if [ "$apply" = true ]; then
            echo "Notifications: rows in flight at the restore point end SUPERSEDED, so nothing sends twice."
            run_in_job python manage.py reconcile_notifications --restored-to "$restore_time" --apply
        else
            echo "Notifications (dry run; add --apply when the counts look right):"
            run_in_job python manage.py reconcile_notifications --restored-to "$restore_time"
        fi
        ;;
    check)
        echo "On: $(database_host)"
        run_in_job python manage.py release_check
        ;;
    hold-off)
        [ "$(variable RECOVERY_HOLD)" = "true" ] || { echo "No hold is on."; exit 0; }
        echo "Reopens the service, on the selected server. Notifications return to the variable"
        echo "NOTIFICATIONS_MODE: '$(variable NOTIFICATIONS_MODE)'. Set it to off first for a staged return."
        set_variable RECOVERY_HOLD false
        deploy_infrastructure
        echo "Then, through the public host (the app's own address answers 401 by design):"
        echo "  python infrastructure/scripts/acceptance_smoke.py --base-url https://<public-host> --expect-client-id <id>"
        ;;
    *)
        echo "Unknown step: ${step} (--help)" >&2
        exit 2
        ;;
esac
