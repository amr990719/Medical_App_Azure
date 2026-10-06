# syntax=docker/dockerfile:1
# Django backend image (PROMPT.md §31, §37).
#   builder  wheels for requirements/prod.txt (no compilers reach the runtime image)
#   runtime  production: slim, non-root, Gunicorn, collectstatic at build time, health check,
#            never migrates on start (`migrate` / `cleanup` modes run as Container Apps jobs)
#   dev      docker compose: runserver, source bind-mounted, development settings
#
#   docker build --target runtime -t medical-backend backend/

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# --- builder ----------------------------------------------------------------------------------
FROM base AS builder
COPY requirements/ requirements/
RUN pip wheel --wheel-dir /wheels -r requirements/prod.txt

# --- runtime (production) ---------------------------------------------------------------------
FROM base AS runtime
# Wheels are bind-mounted from the builder, so they never become an image layer.
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    --mount=type=bind,source=requirements,target=/tmp/requirements \
    pip install --no-index --find-links=/wheels -r /tmp/requirements/prod.txt
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
# Code and static files belong to root and are read-only for the `app` user; nothing in the
# container is state (documents live in Blob Storage, data in PostgreSQL).
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.base DJANGO_SECRET_KEY=collectstatic-build-only \
        python manage.py collectstatic --noinput \
    && chmod 0755 /app/entrypoint.sh
ENV DJANGO_SETTINGS_MODULE=config.settings.production \
    RUN_MIGRATIONS_ON_START=false \
    SEED_ON_START=false \
    PORT=8000
USER app:app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/', timeout=4)"]
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]

# --- dev (docker compose) ---------------------------------------------------------------------
FROM base AS dev
COPY requirements/ requirements/
RUN pip install -r requirements/dev.txt
RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . .
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings.development \
    RUN_MIGRATIONS_ON_START=true \
    SEED_ON_START=true
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready/', timeout=4).status == 200 else 1)"
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
