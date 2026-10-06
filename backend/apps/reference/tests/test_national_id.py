from datetime import date

import pytest

from apps.reference.constants import Gender
from apps.reference.national_id import (
    INVALID_NATIONAL_ID_MESSAGE,
    InvalidNationalId,
    is_valid_national_id,
    mask_national_id,
    parse_national_id,
)

TODAY = date(2026, 10, 5)

# 2 950123 01 012 3 4 → born 1995-01-23, Cairo, sequence digit 13 = 3 (odd → male)
MALE_1995 = "29501230101234"


def test_parses_a_valid_id():
    info = parse_national_id(MALE_1995, today=TODAY)
    assert info.value == MALE_1995
    assert info.date_of_birth == date(1995, 1, 23)
    assert info.birth_year == 1995
    assert info.gender == Gender.MALE
    assert info.governorate_code == "01"
    assert info.governorate_name == "القاهرة"
    assert info.warnings == ()


@pytest.mark.parametrize(
    "raw",
    [
        "٢٩٥٠١٢٣٠١٠١٢٣٤",  # Eastern Arabic digits
        "٢٩٥٠١٢٣ ٠١٠١٢٣٤",  # Eastern Arabic digits with a space
        "295-01-23-0101234",  # dashes
        " 2950123 0101234 ",  # surrounding / inner whitespace
        "٢٩٥٠١٢٣-٠١٠١٢٣٤",  # Review Focus 1: Arabic digits + dash
    ],
)
def test_normalizes_arabic_digits_and_strips_separators(raw):
    assert parse_national_id(raw, today=TODAY).value == MALE_1995


def test_century_2_is_1900s_and_3_is_2000s():
    assert parse_national_id("29501230101234", today=TODAY).birth_year == 1995
    assert parse_national_id("30503150101234", today=TODAY).birth_year == 2005


@pytest.mark.parametrize(
    ("digit13", "gender"),
    [("1", Gender.MALE), ("9", Gender.MALE), ("2", Gender.FEMALE), ("0", Gender.FEMALE)],
)
def test_gender_from_digit_13(digit13, gender):
    raw = "2950123010" + "12" + digit13 + "4"
    assert parse_national_id(raw, today=TODAY).gender == gender


def test_invalid_date_rejected():
    with pytest.raises(InvalidNationalId):
        parse_national_id("29502300101234", today=TODAY)  # 30 February


def test_future_date_rejected():
    with pytest.raises(InvalidNationalId):
        parse_national_id("32610060101234", today=TODAY)  # 2026-10-06 is tomorrow


def test_today_is_accepted():
    assert parse_national_id("32610050101234", today=TODAY).date_of_birth == TODAY


def test_unknown_governorate_is_warning_not_error():
    info = parse_national_id("29501239901234", today=TODAY)
    assert info.governorate_code == "99"
    assert info.governorate_name is None
    assert len(info.warnings) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "2950123010123",
        "295012301012345",
        "19501230101234",
        "49501230101234",
        "2950123010123x",
        None,
    ],
)
def test_wrong_length_century_or_characters_raise(raw):
    with pytest.raises(InvalidNationalId) as exc:
        parse_national_id(raw, today=TODAY)
    assert exc.value.message == INVALID_NATIONAL_ID_MESSAGE
    assert INVALID_NATIONAL_ID_MESSAGE == "الرقم القومي يجب أن يكون 14 رقماً صحيحاً"


def test_check_digit_is_not_validated():
    for last in "0123456789":
        assert is_valid_national_id("2950123010123" + last)


def test_is_valid_national_id():
    assert is_valid_national_id(MALE_1995)
    assert not is_valid_national_id("123")


def test_mask():
    assert mask_national_id("29501230101234") == "29•••••••••234"


def test_mask_never_reveals_short_or_empty_values():
    assert mask_national_id("") == ""
    assert "1234" not in mask_national_id("1234")


def test_error_never_contains_the_raw_value():
    with pytest.raises(InvalidNationalId) as exc:
        parse_national_id("29502300101234", today=TODAY)
    assert "29502300101234" not in str(exc.value)
