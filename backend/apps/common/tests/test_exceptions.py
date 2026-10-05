import pytest

from apps.common.exceptions import (
    ActiveApplicationExists,
    ApplicationNotEditable,
    DomainError,
    DuplicateNationalId,
    InvalidStatusTransition,
    PermissionDeniedError,
    ValidationFailed,
)


def test_envelope_matches_prompt_section_46():
    err = DuplicateNationalId()
    assert err.as_envelope() == {
        "error": {
            "code": "DUPLICATE_NATIONAL_ID",
            "message": "الرقم القومي مسجل لعضو آخر",
            "fields": {"national_id": ["الرقم القومي مسجل لعضو آخر"]},
        }
    }
    assert err.status_code == 409


@pytest.mark.parametrize(
    ("cls", "code", "status"),
    [
        (ValidationFailed, "VALIDATION_ERROR", 400),
        (ApplicationNotEditable, "APPLICATION_NOT_EDITABLE", 409),
        (InvalidStatusTransition, "INVALID_STATUS_TRANSITION", 409),
        (ActiveApplicationExists, "ACTIVE_APPLICATION_EXISTS", 409),
        (PermissionDeniedError, "PERMISSION_DENIED", 403),
    ],
)
def test_codes_and_status(cls, code, status):
    err = cls()
    assert isinstance(err, DomainError)
    assert err.code == code
    assert err.status_code == status
    assert err.message  # always an Arabic, user-facing message


def test_custom_message_and_fields():
    err = ValidationFailed(fields={"birth_year": ["سنة الميلاد غير صحيحة"]})
    assert err.as_envelope()["error"]["fields"] == {"birth_year": ["سنة الميلاد غير صحيحة"]}
    err = InvalidStatusTransition("رسالة")
    assert err.message == "رسالة"
    assert err.as_envelope()["error"]["fields"] == {}
