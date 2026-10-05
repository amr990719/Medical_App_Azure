"""Serializer fields that accept Eastern Arabic digits and normalize them (PROMPT.md §7.1).

Draft-level checks only (types, formats, lengths); completeness is `applications.validation`'s
job. Digits are never silently dropped.
"""

import re

from rest_framework import serializers

from apps.reference.digits import normalize_digits
from apps.reference.national_id import (
    INVALID_NATIONAL_ID_MESSAGE,
    InvalidNationalId,
    normalize_national_id,
    parse_national_id,
)

MSG_INVALID_YEAR = "السنة يجب أن تكون 4 أرقام"
MSG_INVALID_PHONE = "رقم الهاتف يجب أن يحتوي على أرقام فقط"
MSG_DIGITS_ONLY = "يجب أن يحتوي على أرقام فقط"
_PHONE_SEPARATORS = re.compile(r"[\s\-().]+")


class CollapsedCharField(serializers.CharField):
    """Trim and collapse internal whitespace (names, addresses)."""

    def to_internal_value(self, data):
        return " ".join(super().to_internal_value(data).split())


class DigitsCharField(serializers.CharField):
    """Digits-only identifiers (registration / card numbers), Arabic digits normalized."""

    def to_internal_value(self, data):
        value = normalize_digits(super().to_internal_value(data)).replace(" ", "")
        if value and not re.fullmatch(r"[0-9]+", value):
            raise serializers.ValidationError(MSG_DIGITS_ONLY)
        return value


class YearField(serializers.IntegerField):
    """A 4-digit year given as int or string (Western or Arabic digits). Range rules are the
    validator's (1950..FY, 1920..FY); here only the shape is checked."""

    def __init__(self, **kwargs):
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("required", False)
        kwargs.setdefault("min_value", 1000)
        kwargs.setdefault("max_value", 9999)
        super().__init__(**kwargs)
        self.error_messages.update(
            invalid=MSG_INVALID_YEAR, min_value=MSG_INVALID_YEAR, max_value=MSG_INVALID_YEAR
        )

    def validate_empty_values(self, data):
        if isinstance(data, str) and not data.strip():
            return True, None
        return super().validate_empty_values(data)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = normalize_digits(data).strip()
        return super().to_internal_value(data)


class PhoneField(serializers.CharField):
    """Egyptian mobile: separators removed, Arabic digits normalized, `+20`/`0020` → `0`.
    An incomplete number is kept for the draft; rule 7 reports it at submission."""

    def __init__(self, **kwargs):
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("required", False)
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        from apps.common.arabic import normalize_mobile

        raw = _PHONE_SEPARATORS.sub("", normalize_digits(super().to_internal_value(data)))
        if raw and not re.fullmatch(r"\+?[0-9]{1,16}", raw):
            raise serializers.ValidationError(MSG_INVALID_PHONE)
        return normalize_mobile(raw) or raw


class NationalIdField(serializers.CharField):
    """14-digit Egyptian national ID; Arabic digits, spaces and dashes accepted. Blank → None."""

    def __init__(self, **kwargs):
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("required", False)
        kwargs.setdefault("max_length", 40)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = normalize_national_id(super().to_internal_value(data))
        if not value:
            return None
        try:
            parse_national_id(value)
        except InvalidNationalId:
            raise serializers.ValidationError(INVALID_NATIONAL_ID_MESSAGE) from None
        return value

    def run_validation(self, data=serializers.empty):
        if data == "":
            return None
        return super().run_validation(data)
