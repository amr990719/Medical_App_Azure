"""Liveness and readiness probes (PROMPT.md §38). Public, no session, no authentication."""

import logging

from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger("apps.health")

# Only a success is remembered: migrations never un-apply under a running process, and the probe
# runs every 10 seconds, so the migration graph is built until the schema is ready and not after.
_schema_ready = False


def reset_schema_state() -> None:
    global _schema_ready
    _schema_ready = False


def unapplied_migrations() -> list:
    """This code's migrations the database lacks. The plan covers this code's own leaf nodes, so
    a newer schema (the previous revision while a new release runs its migrate job) is not
    "pending": migrations are expand/contract and that revision keeps serving."""
    executor = MigrationExecutor(connection)
    return executor.migration_plan(executor.loader.graph.leaf_nodes())


def _schema_is_ready() -> bool:
    global _schema_ready
    if not _schema_ready:
        _schema_ready = not unapplied_migrations()
    return _schema_ready


@never_cache
@require_GET
def health(request):
    """Liveness: the process answers. Never touches the database."""
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def ready(request):
    """Readiness: PostgreSQL is reachable and holds every migration this code expects."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        schema_ready = _schema_is_ready()
    except DatabaseError:
        logger.warning("Readiness check failed: database unavailable")
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)
    if not schema_ready:
        logger.warning("Readiness check failed: migrations pending")
        return JsonResponse(
            {"status": "unavailable", "database": "ok", "schema": "pending"}, status=503
        )
    return JsonResponse({"status": "ok", "database": "ok", "schema": "ok"})
