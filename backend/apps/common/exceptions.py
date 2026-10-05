"""Domain errors with stable codes and Arabic messages (PROMPT.md §46).

Services raise these; the DRF exception handler (Session 3) renders `as_envelope()`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldError:
    """One validation problem. `step` is the wizard step (1-5) the field belongs to."""

    step: int
    field: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"step": self.step, "field": self.field, "code": self.code, "message": self.message}


class DomainError(Exception):
    code = "ERROR"
    default_message = "حدث خطأ غير متوقع"
    status_code = 400

    def __init__(
        self,
        message: str | None = None,
        *,
        fields: dict[str, list[str]] | None = None,
        errors: list[FieldError] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.fields = fields or {}
        self.errors = errors or []
        super().__init__(self.message)

    def as_envelope(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "fields": self.fields}}


class ValidationFailed(DomainError):
    code = "VALIDATION_ERROR"
    default_message = "يرجى تصحيح الأخطاء المشار إليها"
    status_code = 400

    @classmethod
    def from_errors(cls, errors: list[FieldError]) -> "ValidationFailed":
        fields: dict[str, list[str]] = {}
        for error in errors:
            fields.setdefault(error.field, []).append(error.message)
        return cls(fields=fields, errors=errors)


class ApplicationNotEditable(DomainError):
    code = "APPLICATION_NOT_EDITABLE"
    default_message = "لا يمكن تعديل الطلب في حالته الحالية"
    status_code = 409


class InvalidStatusTransition(DomainError):
    code = "INVALID_STATUS_TRANSITION"
    default_message = "لا يمكن تغيير حالة الطلب بهذا الشكل"
    status_code = 409


class ActiveApplicationExists(DomainError):
    code = "ACTIVE_APPLICATION_EXISTS"
    default_message = "يوجد طلب نشط لهذه السنة المالية"
    status_code = 409


class DuplicateNationalId(DomainError):
    code = "DUPLICATE_NATIONAL_ID"
    default_message = "الرقم القومي مسجل لعضو آخر"
    status_code = 409

    def __init__(self, message: str | None = None, **kwargs) -> None:
        kwargs.setdefault("fields", {"national_id": [message or self.default_message]})
        super().__init__(message, **kwargs)


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"
    default_message = "ليس لديك صلاحية لهذا الإجراء"
    status_code = 403


class RateLimited(DomainError):
    code = "RATE_LIMITED"
    default_message = "تم تجاوز الحد المسموح من الطلبات، يرجى المحاولة لاحقاً"
    status_code = 429
