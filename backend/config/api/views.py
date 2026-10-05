"""JSON error pages for requests that never reach a DRF view (unknown URLs, CSRF middleware)."""

from django.http import JsonResponse

from .exceptions import (
    MSG_NOT_FOUND,
    MSG_PERMISSION_DENIED,
    MSG_SERVER_ERROR,
    MSG_VALIDATION,
    envelope,
)


def not_found(request, exception=None):
    return JsonResponse(envelope("NOT_FOUND", MSG_NOT_FOUND), status=404)


def permission_denied(request, exception=None):
    return JsonResponse(envelope("PERMISSION_DENIED", MSG_PERMISSION_DENIED), status=403)


def bad_request(request, exception=None):
    return JsonResponse(envelope("VALIDATION_ERROR", MSG_VALIDATION), status=400)


def server_error(request):
    return JsonResponse(envelope("SERVER_ERROR", MSG_SERVER_ERROR), status=500)


def csrf_failure(request, reason=""):
    return JsonResponse(envelope("PERMISSION_DENIED", MSG_PERMISSION_DENIED), status=403)
