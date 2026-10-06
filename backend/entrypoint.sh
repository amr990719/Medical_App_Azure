#!/bin/sh
# Container entrypoint (PROMPT.md §31, §32, §37).
#   RUN_MIGRATIONS_ON_START=true  apply migrations before starting (local development only;
#                                 in Azure migrations run once per deployment as a job)
#   SEED_ON_START=true            run `seed_dev_data` (refused unless DEV_AUTH_ENABLED)
set -eu

attempts=0
until python manage.py check --database default >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
        echo "entrypoint: database not reachable after ${attempts} attempts" >&2
        python manage.py check --database default
        exit 1
    fi
    echo "entrypoint: waiting for the database (${attempts})"
    sleep 2
done

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
    python manage.py migrate --noinput
fi

if [ "${SEED_ON_START:-false}" = "true" ]; then
    python manage.py seed_dev_data
fi

exec "$@"
