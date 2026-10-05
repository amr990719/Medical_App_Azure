"""The §46 error envelope: every API error is {"error": {"code", "message", "fields"}}."""

import logging

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import (
    ApplicationNotEditable,
    DuplicateNationalId,
    FileTooLarge,
    ImageTooSmall,
    OcrUnavailable,
    UnsupportedFileType,
    ValidationFailed,
)
from config.api.exceptions import api_exception_handler


def handle(exc):
    request = APIRequestFactory().get("/api/v1/anything/")
    return api_exception_handler(exc, {"request": request, "view": None})


def assert_envelope(response, status, code):
    assert response.status_code == status
    assert set(response.data) == {"error"}
    error = response.data["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["fields"], dict)
    return error


def test_drf_validation_error_lists_every_field():
    exc = drf.ValidationError({"full_name": ["مطلوب"], "national_id": ["غير صحيح", "مكرر"]})
    error = assert_envelope(handle(exc), 400, "VALIDATION_ERROR")
    assert error["fields"] == {"full_name": ["مطلوب"], "national_id": ["غير صحيح", "مكرر"]}


def test_nested_validation_errors_are_flattened_to_dotted_paths():
    exc = drf.ValidationError(
        {"tier_fees": {"1": {"member": ["رقم صحيح"]}}, "items": [{}, {"x": ["y"]}]}
    )
    error = assert_envelope(handle(exc), 400, "VALIDATION_ERROR")
    assert error["fields"] == {"tier_fees.1.member": ["رقم صحيح"], "items.1.x": ["y"]}


def test_non_dict_validation_error_goes_to_non_field_errors():
    error = assert_envelope(handle(drf.ValidationError("خطأ")), 400, "VALIDATION_ERROR")
    assert error["fields"] == {"non_field_errors": ["خطأ"]}


def test_domain_validation_failed_keeps_step_details():
    from apps.common.exceptions import FieldError

    exc = ValidationFailed.from_errors([FieldError(1, "member.full_name", "TOO_SHORT", "قصير")])
    error = assert_envelope(handle(exc), 400, "VALIDATION_ERROR")
    assert error["fields"] == {"member.full_name": ["قصير"]}
    assert error["errors"] == [
        {"step": 1, "field": "member.full_name", "code": "TOO_SHORT", "message": "قصير"}
    ]


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (DuplicateNationalId(), 409, "DUPLICATE_NATIONAL_ID"),
        (ApplicationNotEditable(), 409, "APPLICATION_NOT_EDITABLE"),
        (FileTooLarge(), 413, "FILE_TOO_LARGE"),
        (UnsupportedFileType(), 415, "UNSUPPORTED_FILE_TYPE"),
        (ImageTooSmall(), 400, "IMAGE_TOO_SMALL"),
        (OcrUnavailable(), 503, "OCR_UNAVAILABLE"),
        (drf.NotAuthenticated(), 401, "NOT_AUTHENTICATED"),
        (drf.AuthenticationFailed(), 401, "NOT_AUTHENTICATED"),
        (drf.PermissionDenied(), 403, "PERMISSION_DENIED"),
        (DjangoPermissionDenied(), 403, "PERMISSION_DENIED"),
        (drf.NotFound(), 404, "NOT_FOUND"),
        (Http404(), 404, "NOT_FOUND"),
        (drf.Throttled(wait=30), 429, "RATE_LIMITED"),
        (drf.MethodNotAllowed("PUT"), 405, "METHOD_NOT_ALLOWED"),
        (drf.UnsupportedMediaType("text/plain"), 415, "UNSUPPORTED_MEDIA_TYPE"),
        (drf.ParseError(), 400, "VALIDATION_ERROR"),
    ],
)
def test_exception_mapping(exc, status, code):
    assert_envelope(handle(exc), status, code)


def test_duplicate_national_id_carries_field_message():
    error = assert_envelope(handle(DuplicateNationalId()), 409, "DUPLICATE_NATIONAL_ID")
    assert error["fields"] == {"national_id": ["الرقم القومي مسجل لعضو آخر"]}


def test_messages_are_arabic_not_drf_english():
    error = assert_envelope(handle(drf.NotAuthenticated()), 401, "NOT_AUTHENTICATED")
    assert "Authentication" not in error["message"]
    assert "تسجيل الدخول" in error["message"]


def test_throttled_sets_retry_after():
    response = handle(drf.Throttled(wait=30))
    assert response["Retry-After"] == "30"


def test_unhandled_exception_returns_generic_500_without_traceback(caplog):
    with caplog.at_level(logging.ERROR):
        response = handle(RuntimeError("secret internals 29501150101234"))
    error = assert_envelope(response, 500, "SERVER_ERROR")
    assert "secret" not in error["message"]
    assert "Traceback" not in str(response.data)
