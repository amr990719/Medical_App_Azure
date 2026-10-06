# syntax=docker/dockerfile:1
# Django backend image. Session 6: the `dev` stage used by docker compose (runserver, source
# bind-mounted, development settings). The production stages (wheels builder + slim non-root
# Gunicorn runtime, collectstatic, healthcheck) are added in Session 7 (docs/plan.md Task 7.6).

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

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
