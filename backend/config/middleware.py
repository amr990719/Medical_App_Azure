"""Request id + structured access log (PROMPT.md §38).

Every response carries `X-Request-ID` (a safe incoming value is propagated). One JSON access
line per request: method, path without query string and with 14+ digit runs masked, status,
latency, internal user UUID. Never cookies, headers or bodies.
"""

import logging
import re
import threading
import time
import uuid

from config.logging import mask_digit_runs

logger = logging.getLogger("apps.access")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_local = threading.local()


def current_request_id() -> str | None:
    return getattr(_local, "request_id", None)


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = incoming if _SAFE_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        _local.request_id = request_id
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            _local.request_id = None
        response["X-Request-ID"] = request_id
        user = getattr(request, "user", None)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": mask_digit_runs(request.path),
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "user_id": str(user.pk) if user is not None and user.is_authenticated else None,
            },
        )
        return response
