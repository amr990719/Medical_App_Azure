"""Egyptian national ID parser/validator (PROMPT.md §13).

Layout: [century][YYMMDD][governorate code x2][sequence x4][check digit]. Digit 13 odd = male.
The check digit (position 14) is NOT validated — the algorithm is unconfirmed (open question 13).
Never log a full national ID; use `mask_national_id`.
"""

import re
from dataclasses import dataclass
from datetime import date

from .constants import BIRTH_GOVERNORATE_CODES, Gender
from .digits import normalize_digits

INVALID_NATIONAL_ID_MESSAGE = "الرقم القومي يجب أن يكون 14 رقماً صحيحاً"
UNKNOWN_GOVERNORATE_WARNING = "كود محافظة الميلاد في الرقم القومي غير معروف"

# Whitespace, ASCII hyphen, underscore and the Unicode dashes U+2010..U+2015.
_SEPARATORS = re.compile("[\\s\\-_‐-―]+")
_FOURTEEN_DIGITS = re.compile(r"[0-9]{14}")
_CENTURIES = {"2": 1900, "3": 2000}
MASK_CHAR = "•"


class InvalidNationalId(ValueError):
    message = INVALID_NATIONAL_ID_MESSAGE

    def __init__(self) -> None:
        # The raw value is deliberately never part of the exception (it may reach logs).
        super().__init__(self.message)


@dataclass(frozen=True)
class NationalIdInfo:
    value: str
    date_of_birth: date
    birth_year: int
    gender: Gender
    governorate_code: str
    governorate_name: str | None
    warnings: tuple[str, ...]


def normalize_national_id(raw: str | None) -> str:
    """Western digits with spaces and dashes removed. Does not validate."""
    return _SEPARATORS.sub("", normalize_digits(raw or ""))


def parse_national_id(raw: str | None, *, today: date | None = None) -> NationalIdInfo:
    value = normalize_national_id(raw)
    if not _FOURTEEN_DIGITS.fullmatch(value) or value[0] not in _CENTURIES:
        raise InvalidNationalId()

    year = _CENTURIES[value[0]] + int(value[1:3])
    try:
        born = date(year, int(value[3:5]), int(value[5:7]))
    except ValueError:
        raise InvalidNationalId() from None
    if born > (today or date.today()):
        raise InvalidNationalId()

    code = value[7:9]
    governorate = BIRTH_GOVERNORATE_CODES.get(code)
    warnings = () if governorate else (UNKNOWN_GOVERNORATE_WARNING,)
    gender = Gender.MALE if int(value[12]) % 2 == 1 else Gender.FEMALE
    return NationalIdInfo(
        value=value,
        date_of_birth=born,
        birth_year=born.year,
        gender=gender,
        governorate_code=code,
        governorate_name=governorate,
        warnings=warnings,
    )


def is_valid_national_id(raw: str | None, *, today: date | None = None) -> bool:
    try:
        parse_national_id(raw, today=today)
    except InvalidNationalId:
        return False
    return True


def mask_national_id(value: str | None) -> str:
    """First 2 + last 3 digits only: `29•••••••••234`."""
    if not value:
        return ""
    if len(value) < 14:
        return MASK_CHAR * len(value)
    return value[:2] + MASK_CHAR * (len(value) - 5) + value[-3:]
