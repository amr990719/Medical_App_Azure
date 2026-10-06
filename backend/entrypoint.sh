#!/bin/sh
# Container entrypoint (PROMPT.md §31, §32, §37). The first argument selects the mode:
#   web       Gunicorn (production image default). Never migrates: RUN_MIGRATIONS_ON_START=true
#             is refused, because replicas must not race to migrate.
#   migrate   `manage.py migrate` + `createcachetable`, exactly once per deployment (Container
#             Apps job, run before traffic shifts to the new revision).
#   cleanup   `manage.py cleanup_blobs` (scheduled Container Apps job); extra args are passed on.
#   anything else is executed as given (docker compose dev: runserver). In that case only:
#     RUN_MIGRATIONS_ON_START=true  apply migrations first (local development only)
#     SEED_ON_START=true            run `seed_dev_data` (refused unless DEV_AUTH_ENABLED)
set -eu

wait_for_database() {
    attempts=0
    until python manage.py check --database default >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge "${DB_WAIT_ATTEMPTS:-30}" ]; then
            echo "entrypoint: database not reachable after ${attempts} attempts" >&2
            python manage.py check --database default
            exit 1
        fi
        echo "entrypoint: waiting for the database (${attempts})"
        sleep 2
    done
}

mode="${1:-web}"
case "$mode" in
    web)
        if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
            echo "entrypoint: refusing RUN_MIGRATIONS_ON_START in web mode; run the 'migrate' job" >&2
            exit 1
        fi
        exec gunicorn config.wsgi:application --config python:config.gunicorn
        ;;
    migrate)
        wait_for_database
        python manage.py migrate --noinput
        # Table of the shared throttle cache (CACHE_URL=dbcache://django_cache in Azure, Q-T6);
        # idempotent, and a no-op when no database cache is configured.
        exec python manage.py createcachetable
        ;;
    cleanup)
        shift
        exec python manage.py cleanup_blobs "$@"
        ;;
esac

wait_for_database

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
    python manage.py migrate --noinput
fi

if [ "${SEED_ON_START:-false}" = "true" ]; then
    python manage.py seed_dev_data
fi

exec "$@"
