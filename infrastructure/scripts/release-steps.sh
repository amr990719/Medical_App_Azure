#!/usr/bin/env bash
# The steps of a release, called by .github/workflows/release-production.yml and the dev deploy
# workflows (docs/production-runbook.md). Every image is copied by digest with skopeo, which keeps
# the manifest bytes, so production runs exactly what dev ran.
#
#   registry-login <acr>
#   export-artifact <acr> <repository> <tag> <out-dir>            prints the digest
#   import-artifact <acr> <repository> <tag> <dir> <digest>       refuses a digest that changed
#   store-frontend <acr> <dist-dir> <tag>                         prints the digest
#   unpack-frontend <artifact-dir> <out-dir>                      prints the content hash
#   content-hash <dir>
#   digest-of <acr> <repository> <tag>                            empty when the tag does not exist
#   current-release <acr>                                         empty before the first release
#   released-digest <acr> <sha> backend|frontend                  from that release's manifest
#   export-params                                                 VARS_JSON -> $GITHUB_ENV
#   redact <file>                                                 masks identifiers in place
#   run-migrations <job> <resource-group> <image>
#   update-job-image <job> <resource-group> <image>
#   create-revision <app> <resource-group> <image> <suffix>
#   store-manifest <acr> <manifest.json> <sha>                    moves :current and :previous
#
# Tokens are never printed. Requires az, skopeo, docker, python3.
set -euo pipefail

ACR_TOKEN_USER="00000000-0000-0000-0000-000000000000"
MANIFEST_REPOSITORY="medical-release"
CONTENT_LABEL="medical.content-sha256"
SOURCE_LABEL="medical.source-sha"
BACKEND_LABEL="medical.backend-digest"
FRONTEND_LABEL="medical.frontend-digest"
# What the parameter files read from the GitHub environment. ALERT_EMAIL is an environment secret
# and CONTAINER_IMAGE and DEPLOY_WEB_APP are set by each step.
PARAM_VARS='["CONTAINER_APP_NAME","ENTRA_AUTHORITY","ENTRA_TENANT_ID","ENTRA_CLIENT_ID","PUBLIC_HOSTNAME","STATIC_WEB_APP_LOCATION","ENABLE_OCR","ENABLE_PRIVATE_NETWORKING","POSTGRES_ENTRA_ADMIN_OBJECT_ID","POSTGRES_ENTRA_ADMIN_NAME","POSTGRES_ENTRA_ADMIN_TYPE","ENABLE_NOTIFICATIONS","NOTIFICATIONS_MODE","SES_ACCESS_KEY_FROM_KEY_VAULT","SES_REGION","SES_FROM_ADDRESS","RECOVERY_HOLD","POSTGRES_SERVER_NAME_OVERRIDE","ENABLE_SERVICE_ALERTS"]'

# `docker push` may publish a multi-platform index (it does with Docker Desktop's image store), and
# by default skopeo would copy only one platform out of it, which changes the digest.
copy() {
    skopeo copy --quiet --preserve-digests --multi-arch all "$@"
}

python_bin() {
    if command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi
}

login_server() {
    az acr show --name "$1" --query loginServer -o tsv
}

registry_login() {
    local acr="$1" server token
    # GitHub's ubuntu-24.04 image lists skopeo; this only guards against that changing.
    if ! command -v skopeo >/dev/null 2>&1; then
        sudo apt-get update -qq && sudo apt-get install -y -qq skopeo >/dev/null
    fi
    server="$(login_server "$acr")"
    token="$(az acr login --name "$acr" --expose-token --query accessToken -o tsv)"
    if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::add-mask::${token}"; fi
    printf '%s' "$token" | skopeo login "$server" --username "$ACR_TOKEN_USER" --password-stdin >/dev/null
    printf '%s' "$token" | docker login "$server" --username "$ACR_TOKEN_USER" --password-stdin >/dev/null 2>&1
}

# Empty output means the tag is absent. Any other failure stops the release: "cannot read" must
# never be mistaken for "no release yet".
inspect_or_empty() {
    local reference="$1" format="$2" output
    if output="$(skopeo inspect --format "$format" "docker://${reference}" 2>&1)"; then
        printf '%s\n' "$output"
        return 0
    fi
    case "$output" in
        *"manifest unknown"* | *"name unknown"* | *"repository name not known"* | *"not found"*)
            return 0 ;;
    esac
    printf '%s\n' "$output" >&2
    return 1
}

digest_of() {
    inspect_or_empty "$(login_server "$1")/$2:$3" '{{.Digest}}'
}

export_artifact() {
    local acr="$1" repository="$2" tag="$3" out_dir="$4" server digest
    server="$(login_server "$acr")"
    digest="$(digest_of "$acr" "$repository" "$tag")"
    if [ -z "$digest" ]; then
        echo "::error::${repository}:${tag} is not in the ${acr} registry. Was this commit deployed to dev?" >&2
        return 1
    fi
    mkdir -p "$out_dir"
    copy "docker://${server}/${repository}@${digest}" "dir:${out_dir}" >&2
    printf '%s\n' "$digest"
}

import_artifact() {
    local acr="$1" repository="$2" tag="$3" dir="$4" expected="$5" server actual
    server="$(login_server "$acr")"
    copy "dir:${dir}" "docker://${server}/${repository}:${tag}"
    actual="$(digest_of "$acr" "$repository" "$tag")"
    if [ "$actual" != "$expected" ]; then
        echo "::error::${repository}:${tag} has digest ${actual}, expected ${expected}" >&2
        return 1
    fi
    echo "Imported ${repository}@${expected}"
}

content_hash() {
    (cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
}

# The built site as a scratch image: never run, stored and copied exactly like the backend, so its
# identity is a digest and it outlives GitHub's artifact retention.
store_frontend() {
    local acr="$1" dist="$2" tag="$3" server image hash digest
    server="$(login_server "$acr")"
    image="${server}/medical-frontend:${tag}"
    digest="$(digest_of "$acr" medical-frontend "$tag")"
    if [ -n "$digest" ]; then
        echo "${image} already exists; a tag is never overwritten" >&2
        printf '%s\n' "$digest"
        return 0
    fi
    hash="$(content_hash "$dist")"
    printf 'FROM scratch\nLABEL %s="%s"\nCOPY . /site/\n' "$CONTENT_LABEL" "$hash" |
        docker build --quiet --tag "$image" --file - "$dist" >&2
    docker push --quiet "$image" >&2
    digest_of "$acr" medical-frontend "$tag"
}

unpack_frontend() {
    local artifact="$1" out="$2" python expected actual layer
    python="$(python_bin)"
    expected="$(skopeo inspect --format "{{ index .Labels \"${CONTENT_LABEL}\" }}" "dir:${artifact}")"
    layer="$("$python" - "$artifact" <<'PY'
import json
import sys

artifact = sys.argv[1]
with open(f"{artifact}/manifest.json", encoding="utf-8") as handle:
    manifest = json.load(handle)
if "manifests" in manifest:  # an index: the site is the linux/amd64 instance, not an attestation
    instance = next(
        m for m in manifest["manifests"]
        if m.get("platform", {}).get("os") == "linux"
        and m.get("platform", {}).get("architecture") == "amd64"
    )
    name = instance["digest"].split(":")[1]
    with open(f"{artifact}/{name}.manifest.json", encoding="utf-8") as handle:
        manifest = json.load(handle)
layers = manifest["layers"]
assert len(layers) == 1, "the frontend artifact must have exactly one layer"
print(layers[0]["digest"].split(":")[1])
PY
)"
    local staging
    staging="$(mktemp -d)"
    tar -xf "${artifact}/${layer}" -C "$staging"
    mkdir -p "$out"
    cp -R "${staging}/site/." "$out/"
    rm -rf "$staging"
    actual="$(content_hash "$out")"
    if [ "$actual" != "$expected" ]; then
        echo "::error::the frontend content hash ${actual} differs from the recorded ${expected}" >&2
        return 1
    fi
    printf '%s\n' "$actual"
}

current_release() {
    inspect_or_empty "$(login_server "$1")/${MANIFEST_REPOSITORY}:current" \
        "{{ index .Labels \"${SOURCE_LABEL}\" }}"
}

released_digest() {
    local acr="$1" sha="$2" part="$3" label
    case "$part" in
        backend) label="$BACKEND_LABEL" ;;
        frontend) label="$FRONTEND_LABEL" ;;
        *) echo "unknown part ${part}" >&2; return 2 ;;
    esac
    inspect_or_empty "$(login_server "$acr")/${MANIFEST_REPOSITORY}:${sha}" "{{ index .Labels \"${label}\" }}"
}

export_params() {
    : "${VARS_JSON:?VARS_JSON is required}" "${GITHUB_ENV:?GITHUB_ENV is required}"
    printf '%s' "$VARS_JSON" | jq -r --argjson keys "$PARAM_VARS" \
        'to_entries[] | select(.key as $k | $keys | index($k)) | select(.value != "") | "\(.key)=\(.value)"' \
        >>"$GITHUB_ENV"
}

# Public repository: run logs and step summaries are public. Removes the identifiers named in
# REDACT_VALUES (newline separated) and, whatever the input, anything shaped like an email address.
redact() {
    "$(python_bin)" - "$1" <<'PY'
import os, re, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    text = handle.read()
for value in os.environ.get("REDACT_VALUES", "").splitlines():
    if value.strip():
        text = text.replace(value.strip(), "***")
text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "***", text)
text = re.sub(r"\x1b\[[0-9;]*m", "", text)
with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
PY
}

wait_for_execution() {
    local job="$1" resource_group="$2" execution="$3" deadline status
    deadline=$((SECONDS + 1800))
    while :; do
        status="$(az containerapp job execution show --name "$job" --resource-group "$resource_group" \
            --job-execution-name "$execution" --query properties.status -o tsv)"
        case "$status" in
            Succeeded) return 0 ;;
            Failed | Stopped | Degraded)
                echo "::error::Execution ${execution} of ${job} ended ${status}. Logs: Log Analytics, ContainerAppConsoleLogs_CL where ContainerJobName_s == '${job}'" >&2
                return 1 ;;
        esac
        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "::error::Execution ${execution} of ${job} is still '${status}' after 30 minutes" >&2
            return 1
        fi
        sleep 15
    done
}

run_migrations() {
    local job="$1" resource_group="$2" image="$3" execution
    az containerapp job update --name "$job" --resource-group "$resource_group" --image "$image" --output none
    execution="$(az containerapp job start --name "$job" --resource-group "$resource_group" --query name -o tsv)"
    echo "Started migration execution ${execution}"
    wait_for_execution "$job" "$resource_group" "$execution"
    echo "Migrations applied"
}

update_job_image() {
    az containerapp job update --name "$1" --resource-group "$2" --image "$3" --output none
}

create_revision() {
    local app="$1" resource_group="$2" image="$3" suffix="$4" revision deadline health
    az containerapp update --name "$app" --resource-group "$resource_group" --image "$image" \
        --revision-suffix "$suffix" --output none
    revision="${app}--${suffix}"
    deadline=$((SECONDS + 900))
    while :; do
        health="$(az containerapp revision show --name "$app" --resource-group "$resource_group" \
            --revision "$revision" --query properties.healthState -o tsv)"
        [ "$health" = "Healthy" ] && break
        if [ "$health" = "Unhealthy" ] || [ "$SECONDS" -ge "$deadline" ]; then
            echo "::error::Revision ${revision} is '${health}'. In single-revision mode the previous revision keeps serving until a new one is ready." >&2
            return 1
        fi
        sleep 15
    done
    echo "Revision ${revision} is healthy"
}

# The record of what production runs, kept beside the artifacts in the production registry:
# medical-release:<sha>, plus :current and :previous, which the order check and a rollback read.
store_manifest() {
    local acr="$1" manifest="$2" sha="$3" server context backend frontend python digest
    server="$(login_server "$acr")"
    python="$(python_bin)"
    backend="$("$python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["backend"]["digest"])' "$manifest")"
    frontend="$("$python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["frontend"]["digest"])' "$manifest")"
    context="$(mktemp -d)"
    cp "$manifest" "${context}/release-manifest.json"
    {
        printf 'FROM scratch\n'
        printf 'LABEL %s="%s" %s="%s" %s="%s"\n' \
            "$SOURCE_LABEL" "$sha" "$BACKEND_LABEL" "$backend" "$FRONTEND_LABEL" "$frontend"
        printf 'COPY release-manifest.json /release-manifest.json\n'
    } | docker build --quiet --tag "${server}/${MANIFEST_REPOSITORY}:${sha}" --file - "$context" >&2
    rm -rf "$context"
    # A re-run of the same release must not make "previous" point at itself.
    digest="$(digest_of "$acr" "$MANIFEST_REPOSITORY" current)"
    if [ -n "$digest" ] && [ "$(current_release "$acr")" != "$sha" ]; then
        copy "docker://${server}/${MANIFEST_REPOSITORY}:current" \
            "docker://${server}/${MANIFEST_REPOSITORY}:previous"
    fi
    docker push --quiet "${server}/${MANIFEST_REPOSITORY}:${sha}" >&2
    copy "docker://${server}/${MANIFEST_REPOSITORY}:${sha}" \
        "docker://${server}/${MANIFEST_REPOSITORY}:current"
    echo "Recorded the release ${sha} as ${MANIFEST_REPOSITORY}:current"
}

usage() {
    sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

command="${1:-}"
[ $# -gt 0 ] && shift
case "$command" in
    registry-login) registry_login "$@" ;;
    export-artifact) export_artifact "$@" ;;
    import-artifact) import_artifact "$@" ;;
    store-frontend) store_frontend "$@" ;;
    unpack-frontend) unpack_frontend "$@" ;;
    content-hash) content_hash "$@" ;;
    digest-of) digest_of "$@" ;;
    current-release) current_release "$@" ;;
    released-digest) released_digest "$@" ;;
    export-params) export_params ;;
    redact) redact "$@" ;;
    run-migrations) run_migrations "$@" ;;
    update-job-image) update_job_image "$@" ;;
    create-revision) create_revision "$@" ;;
    store-manifest) store_manifest "$@" ;;
    *) usage; [ -z "$command" ] || { echo "Unknown step: ${command}" >&2; exit 2; } ;;
esac
