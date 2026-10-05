"""DRF exception handler rendering the PROMPT.md §46 envelope.

`{"error": {"code": "...", "message": "<Arabic>", "fields": {"path": ["<Arabic>"]}}}` for every
error, with stable codes. Unhandled exceptions become a generic 500 and are logged (the logging
filter masks national IDs); no traceback or internal message ever reaches the client.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf
from rest_framework import status
from rest_framework.response import Response

from apps.common.exceptions import DomainError

logger = logging.getLogger("apps.api")

MSG_VALIDATION = "يرجى تصحيح الأخطاء المشار إليها"
MSG_NOT_AUTHENTICATED = "يرجى تسجيل الدخول للمتابعة"
MSG_PERMISSION_DENIED = "ليس لديك صلاحية لهذا الإجراء"
MSG_NOT_FOUND = "العنصر المطلوب غير موجود"
MSG_RATE_LIMITED = "تم تجاوز الحد المسموح من الطلبات، يرجى المحاولة لاحقاً"
MSG_METHOD_NOT_ALLOWED = "طريقة الطلب غير مسموح بها"
MSG_UNSUPPORTED_MEDIA = "صيغة الطلب غير مدعومة"
MSG_SERVER_ERROR = "حدث خطأ غير متوقع، يرجى المحاولة لاحقاً"

# DRF exception class → (code, Arabic message). Order matters: subclasses first.
_DRF_MAP: list[tuple[type[drf.APIException], str, str]] = [
    (drf.NotAuthenticated, "NOT_AUTHENTICATED", MSG_NOT_AUTHENTICATED),
    (drf.AuthenticationFailed, "NOT_AUTHENTICATED", MSG_NOT_AUTHENTICATED),
    (drf.PermissionDenied, "PERMISSION_DENIED", MSG_PERMISSION_DENIED),
    (drf.NotFound, "NOT_FOUND", MSG_NOT_FOUND),
    (drf.Throttled, "RATE_LIMITED", MSG_RATE_LIMITED),
    (drf.MethodNotAllowed, "METHOD_NOT_ALLOWED", MSG_METHOD_NOT_ALLOWED),
    (drf.UnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", MSG_UNSUPPORTED_MEDIA),
    (drf.NotAcceptable, "NOT_ACCEPTABLE", MSG_UNSUPPORTED_MEDIA),
    (drf.ParseError, "VALIDATION_ERROR", MSG_VALIDATION),
]


def envelope(code: str, message: str, fields: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "fields": fields or {}}}


def _flatten(detail, prefix: str = "") -> dict[str, list[str]]:
    """DRF error details (nested dicts/lists) → {"dotted.path": [messages]}."""
    if isinstance(detail, dict):
        out: dict[str, list[str]] = {}
        for key, value in detail.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(detail, list):
        if all(not isinstance(item, dict | list) for item in detail):
            return {prefix or "non_field_errors": [str(item) for item in detail]} if detail else {}
        out = {}
        for index, item in enumerate(detail):
            out.update(_flatten(item, f"{prefix}.{index}" if prefix else str(index)))
        return out
    return {prefix or "non_field_errors": [str(detail)]}


def api_exception_handler(exc, context) -> Response:
    if isinstance(exc, DomainError):
        return Response(exc.as_envelope(), status=exc.status_code)

    if isinstance(exc, drf.ValidationError):
        return Response(
            envelope("VALIDATION_ERROR", MSG_VALIDATION, _flatten(exc.detail)),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, Http404):
        exc = drf.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf.PermissionDenied()

    if isinstance(exc, drf.APIException):
        code, message = "ERROR", MSG_SERVER_ERROR
        for cls, mapped_code, mapped_message in _DRF_MAP:
            if isinstance(exc, cls):
                code, message = mapped_code, mapped_message
                break
        headers = {}
        if isinstance(exc, drf.Throttled) and exc.wait is not None:
            headers["Retry-After"] = str(int(exc.wait))
        if getattr(exc, "auth_header", None):
            headers["WWW-Authenticate"] = exc.auth_header
        return Response(envelope(code, message), status=exc.status_code, headers=headers)

    request = context.get("request")
    logger.exception(
        "Unhandled API exception",
        extra={"path": getattr(request, "path", ""), "exception_type": type(exc).__name__},
    )
    return Response(
        envelope("SERVER_ERROR", MSG_SERVER_ERROR), status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
