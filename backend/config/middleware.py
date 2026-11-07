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


def _has_port(entry: str) -> bool:
    """`192.0.2.1:443` or `[2001:db8::1]:443`; a bare IPv6 address has colons but no port."""
    return "]:" in entry if entry.startswith("[") else entry.count(":") == 1


class ForwardedChainDiagnosticsMiddleware:
    """PROXY-1 / Q-T13: how many X-Forwarded-For entries reach Django, so `TRUSTED_PROXY_COUNT`
    can be set from evidence. Off unless PROXY_DIAGNOSTICS_ENABLED. Counts and a short keyed
    hash of the derived client address (the throttle key) only, never an address or a port."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("apps.proxy")

    def __call__(self, request):
        from django.conf import settings

        if settings.PROXY_DIAGNOSTICS_ENABLED:
            self._log(request, settings)
        return self.get_response(request)

    def _log(self, request, settings) -> None:
        import hashlib
        import hmac

        from rest_framework.settings import api_settings

        from apps.common.client_ip import client_ip

        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
        key = hmac.new(settings.SECRET_KEY.encode(), client_ip(request).encode(), hashlib.sha256)
        self.logger.info(
            "forwarded_chain",
            extra={
                "request_id": getattr(request, "request_id", None),
                "path": mask_digit_runs(request.path),
                "xff_entries": len(entries),
                "xff_entries_with_port": sum(_has_port(entry) for entry in entries),
                "trusted_proxies": api_settings.NUM_PROXIES or 0,
                "client_key": key.hexdigest()[:12],
                "cache_backend": settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1],
            },
        )


class HealthProbeMiddleware:
    """First in MIDDLEWARE: answers `GET /api/health/` and `/api/ready/` before host validation
    and the HTTPS redirect. Platform probes (Container Apps, Docker HEALTHCHECK) reach a replica
    by IP or `localhost` over plain HTTP; ALLOWED_HOSTS stays strict for everything else. Probe
    responses carry no data and are not access-logged (they would flood the logs)."""

    def __init__(self, get_response):
        from config import health

        self.get_response = get_response
        self._probes = {"/api/health/": health.health, "/api/ready/": health.ready}

    def __call__(self, request):
        probe = self._probes.get(request.path_info)
        if probe is not None and request.method == "GET":
            return probe(request)
        return self.get_response(request)


API_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


class ContentSecurityPolicyMiddleware:
    """Production: the API only returns JSON and document bytes, so nothing it serves may load
    scripts, styles or frames (PROMPT.md §30). The SPA's own CSP is set by Static Web Apps."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", API_CONTENT_SECURITY_POLICY)
        return response


class RequestBodyLimitMiddleware:
    """Refuses a request whose declared body exceeds MAX_UPLOAD_BYTES (+ MULTIPART_OVERHEAD_BYTES
    for the form fields) with 413, before anything reads it. Django enforces upload sizes only
    after parsing, and spools files above FILE_UPLOAD_MAX_MEMORY_SIZE to the replica's disk, so a
    signed-in user could otherwise send gigabytes. Without Content-Length Django reads no body."""

    def __init__(self, get_response):
        from django.conf import settings

        self.get_response = get_response
        self.limit = settings.MAX_UPLOAD_BYTES + settings.MULTIPART_OVERHEAD_BYTES

    def __call__(self, request):
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            declared = 0
        if declared > self.limit:
            from django.http import JsonResponse

            from apps.documents.validators import too_large_error

            error = too_large_error()
            return JsonResponse(
                error.as_envelope(),
                status=error.status_code,
                json_dumps_params={"ensure_ascii": False},
            )
        return self.get_response(request)
