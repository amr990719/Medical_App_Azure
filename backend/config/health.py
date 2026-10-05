"""Liveness and readiness probes (PROMPT.md §38). Public, no session, no authentication."""

import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger("apps.health")


@never_cache
@require_GET
def health(request):
    """Liveness: the process answers. Never touches the database."""
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def ready(request):
    """Readiness: PostgreSQL is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.warning("Readiness check failed: database unavailable")
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
