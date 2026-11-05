#!/usr/bin/env bash
# Promotion for real: two local registries stand in for the dev and production ACRs, with real
# skopeo and docker and only `az` stubbed. Proves the claim everything rests on: production receives
# the exact bytes dev ran, and the order and rollback records read back correctly.
#
# Run from the repository root; needs Docker and an image tagged medical-backend:lock-check
# (`docker build --target runtime -t medical-backend:lock-check backend`):
#
#   bash infrastructure/tests/promotion_integration.sh
#
# It starts its own containers on ports 5100 and 5101 and removes them afterwards.
set -euo pipefail

if [ "${1:-}" != "--inside" ]; then
    REPO="$(pwd -W 2>/dev/null || pwd)"
    cleanup() { docker rm -f promotion-dev promotion-prod >/dev/null 2>&1 || true; }
    trap cleanup EXIT
    cleanup
    docker run -d --name promotion-dev -p 5100:5000 mirror.gcr.io/library/registry:2 >/dev/null
    docker run -d --name promotion-prod -p 5101:5000 mirror.gcr.io/library/registry:2 >/dev/null
    # Docker Desktop on Windows: keep Git Bash from rewriting the container paths below.
    MSYS_NO_PATHCONV=1 docker run --rm --network host \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "${REPO}:/repo:ro" \
        mirror.gcr.io/library/docker:cli \
        sh -c 'apk add --quiet bash skopeo python3 coreutils findutils tar >/dev/null && bash /repo/infrastructure/tests/promotion_integration.sh --inside'
    exit 0
fi

mkdir -p /stub /etc/containers
cat >/etc/containers/registries.conf <<'CONF'
[[registry]]
location = "localhost:5100"
insecure = true
[[registry]]
location = "localhost:5101"
insecure = true
CONF
cat >/stub/az <<'STUB'
#!/bin/sh
# `az acr show -n <dev|prod>` and `az acr login --expose-token`; nothing else is expected.
case "$*" in
    "acr show --name dev --query loginServer -o tsv") echo localhost:5100 ;;
    "acr show --name prod --query loginServer -o tsv") echo localhost:5101 ;;
    "acr login "*) echo not-a-real-token ;;
    *) echo "unexpected az call: $*" >&2; exit 1 ;;
esac
STUB
chmod +x /stub/az
export PATH="/stub:${PATH}"

steps=/repo/infrastructure/scripts/release-steps.sh
gate=/repo/infrastructure/scripts/release_gate.py
work="$(mktemp -d)"
source_sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
next_sha=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
passed=0

check() { # description expected actual
    if [ "$2" != "$3" ]; then
        echo "FAIL $1: expected '$2', got '$3'" >&2
        exit 1
    fi
    echo "PASS $1"
    passed=$((passed + 1))
}

refuses() { # description command...
    local description="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "FAIL $description: it should have been refused" >&2
        exit 1
    fi
    echo "PASS $description"
    passed=$((passed + 1))
}

bash "$steps" registry-login dev 2>/dev/null || true

# --- What the dev deploy workflows do ----------------------------------------------------------
check "a tag that does not exist reads as empty" "" "$(bash "$steps" digest-of dev medical-backend "$source_sha")"
docker tag medical-backend:lock-check "localhost:5100/medical-backend:${source_sha}"
docker push --quiet "localhost:5100/medical-backend:${source_sha}" >/dev/null
backend_digest="$(bash "$steps" digest-of dev medical-backend "$source_sha")"
echo "dev backend ${backend_digest}"

mkdir -p "${work}/dist/assets"
echo '<html lang="ar" dir="rtl"></html>' >"${work}/dist/index.html"
echo 'console.log(1)' >"${work}/dist/assets/a.js"
echo '{}' >"${work}/dist/staticwebapp.config.json"
frontend_digest="$(bash "$steps" store-frontend dev "${work}/dist" "$source_sha")"
echo "dev frontend ${frontend_digest}"
check "storing the same build twice never overwrites" "$frontend_digest" \
    "$(bash "$steps" store-frontend dev "${work}/dist" "$source_sha" 2>/dev/null)"

# --- What the export job does -------------------------------------------------------------------
check "export names the digest for the backend" "$backend_digest" \
    "$(bash "$steps" export-artifact dev medical-backend "$source_sha" "${work}/artifacts/backend")"
check "export names the digest for the frontend" "$frontend_digest" \
    "$(bash "$steps" export-artifact dev medical-frontend "$source_sha" "${work}/artifacts/frontend")"
refuses "an artifact dev never built cannot be exported" \
    bash "$steps" export-artifact dev medical-backend "$next_sha" "${work}/artifacts/missing"

# --- What the deploy job does -------------------------------------------------------------------
check "before the first release, production has no current release" "" "$(bash "$steps" current-release prod)"
bash "$steps" import-artifact prod medical-backend "$source_sha" "${work}/artifacts/backend" "$backend_digest"
bash "$steps" import-artifact prod medical-frontend "$source_sha" "${work}/artifacts/frontend" "$frontend_digest"
check "production holds the backend with the digest dev ran" "$backend_digest" \
    "$(bash "$steps" digest-of prod medical-backend "$source_sha")"
check "production holds the frontend with the digest dev ran" "$frontend_digest" \
    "$(bash "$steps" digest-of prod medical-frontend "$source_sha")"
refuses "an import with the wrong digest is refused" \
    bash "$steps" import-artifact prod medical-backend wrong "${work}/artifacts/backend" \
    "sha256:0000000000000000000000000000000000000000000000000000000000000000"

content="$(bash "$steps" unpack-frontend "${work}/artifacts/frontend" "${work}/site")"
check "the unpacked site has the content of the build" "$(bash "$steps" content-hash "${work}/dist")" "$content"
check "the unpacked site has its files" '<html lang="ar" dir="rtl"></html>' "$(cat "${work}/site/index.html")"

mkdir -p "${work}/tampered"
cp -R "${work}/artifacts/frontend/." "${work}/tampered/"
mkdir -p "${work}/evil/site"
echo evil >"${work}/evil/site/index.html"
# Replace every stored layer, whichever instance of an index holds the site.
for blob in "${work}"/tampered/*; do
    case "$(basename "$blob")" in
        *.json | version) ;;
        *) if tar -tf "$blob" site/index.html >/dev/null 2>&1; then tar -C "${work}/evil" -czf "$blob" site; fi ;;
    esac
done
refuses "a frontend whose bytes changed in transit is refused" \
    bash "$steps" unpack-frontend "${work}/tampered" "${work}/site-tampered"

# --- The release record -------------------------------------------------------------------------
echo '{}' >"${work}/evidence.json"
record() { # sha previous output
    python3 "$gate" manifest --sha "$1" --mode release --backend-digest "$backend_digest" \
        --frontend-digest "$frontend_digest" --frontend-content-sha256 "$content" --previous "$2" \
        --dev-acceptance "record of the test" --evidence-file "${work}/evidence.json" \
        --run-url https://example.test/run --actor test --output "$3" >/dev/null
    bash "$steps" store-manifest prod "$3" "$1"
}
record "$source_sha" "" "${work}/first.json"
check "the first release becomes current" "$source_sha" "$(bash "$steps" current-release prod)"
check "a rollback can find a released backend" "$backend_digest" "$(bash "$steps" released-digest prod "$source_sha" backend)"
check "a rollback can find a released frontend" "$frontend_digest" "$(bash "$steps" released-digest prod "$source_sha" frontend)"
check "a commit never released has no digest for a rollback" "" "$(bash "$steps" released-digest prod "$next_sha" backend)"

record "$source_sha" "" "${work}/rerun.json"
check "re-running a release keeps it current" "$source_sha" "$(bash "$steps" current-release prod)"
check "re-running a release does not invent a previous one" "" "$(bash "$steps" digest-of prod medical-release previous)"

record "$next_sha" "$source_sha" "${work}/second.json"
check "the next release becomes current" "$next_sha" "$(bash "$steps" current-release prod)"
previous="$(skopeo inspect --format '{{ index .Labels "medical.source-sha" }}' docker://localhost:5101/medical-release:previous)"
check "the release before it is kept as previous" "$source_sha" "$previous"

# --- Secrets stay out of public output ----------------------------------------------------------
printf 'sub 11111111-2222 owner@example.test in \033[32mgreen\033[0m\n' >"${work}/report.txt"
REDACT_VALUES="11111111-2222" bash "$steps" redact "${work}/report.txt"
check "a report has identifiers, addresses and colour codes removed" "sub *** *** in green" "$(cat "${work}/report.txt")"

echo "promotion integration: ${passed} checks passed"
