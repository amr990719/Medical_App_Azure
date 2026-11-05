#!/usr/bin/env bash
# Resolve the *.in ranges into the pinned, hash-checked *.txt files the image and CI install.
#
#   backend/requirements/lock.sh            refresh after editing a *.in file (keeps other pins)
#   backend/requirements/lock.sh --upgrade  move every pin to the newest allowed version
#   backend/requirements/lock.sh --check    fail if a *.txt no longer matches its *.in (CI)
#
# prod.txt is resolved first, and dev.txt keeps its pins, so tests run the versions production runs.
# Needs uv. Linux and Windows hosts share one lock (--universal).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
mode="${1:-}"

compile() { # input output [extra uv args...]
    local input="$1" output="$2"
    shift 2
    uv pip compile "$input" --output-file "$output" --universal --generate-hashes \
        --python-version 3.12 --quiet --no-header --no-annotate "$@"
}

case "$mode" in
    "" | --upgrade)
        args=()
        if [ "$mode" = --upgrade ]; then args=(--upgrade); fi
        compile prod.in prod.txt "${args[@]+"${args[@]}"}"
        cp prod.txt dev.txt
        compile dev.in dev.txt
        ;;
    --check)
        work="$(mktemp -d)"
        trap 'rm -rf "$work"' EXIT
        for name in prod dev; do
            cp "${name}.txt" "${work}/${name}.txt"
            compile "${name}.in" "${work}/${name}.txt"
            if ! diff -u "${name}.txt" "${work}/${name}.txt"; then
                echo "::error::backend/requirements/${name}.txt is stale: run backend/requirements/lock.sh" >&2
                exit 1
            fi
        done
        echo "requirements locks match their inputs"
        ;;
    *)
        sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
        exit 2
        ;;
esac
