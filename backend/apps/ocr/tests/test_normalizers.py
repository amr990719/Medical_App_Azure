"""OCR normalizers (PROMPT.md §21.4), ported from the prototype's OcrService.js behaviour."""

import pytest

from apps.ocr.normalizers import (
    GENDER_VALUES,
    RELIGION_VALUES,
    SYNDICATE_TYPE_VALUES,
    birth_year_from_id,
    clean_national_id,
    extract_year,
    map_enum,
    map_governorate,
    triple_name,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("29501150101234", "29501150101234"),
        ("٢٩٥٠١١٥٠١٠١٢٣٤", "29501150101234"),
        ("2950 1150 1012 34", "29501150101234"),
        ("الرقم القومي: ٢٩٥٠١١٥-٠١٠١٢٣٤", "29501150101234"),
        ("2950115010123456", "29501150101234"),  # first 14 digits
        ("12345", ""),  # too short: no suggestion rather than a wrong one
        ("", ""),
        (None, ""),
    ],
)
def test_clean_national_id(raw, expected):
    assert clean_national_id(raw) == expected


@pytest.mark.parametrize(
    ("id14", "expected"),
    [("29501150101234", 1995), ("31503100101234", 2015), ("19501150101234", None), ("123", None)],
)
def test_birth_year_from_id(id14, expected):
    assert birth_year_from_id(id14) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("٢٠٢١-٠٤-٢٨", 2021),
        ("2021/04/28", 2021),
        ("تاريخ القيد ٢٠٢١-٠٤-٢٨", 2021),
        ("٢٨-٠٤-٢٠٢١", 2021),
        ("28/4/1999", 1999),
        ("1988", 1988),
        ("٢٠١٥", 2015),
        ("مواليد 3 مارس 2015 القاهرة", 2015),
        ("0428", None),  # four digits, but not a plausible year
        ("", None),
        (None, None),
    ],
)
def test_extract_year(raw, expected):
    assert extract_year(raw) == expected


@pytest.mark.parametrize(
    ("full", "expected"),
    [
        ("عبد الرحمن محمد علي أحمد", "عبد الرحمن محمد علي"),
        ("أبو بكر محمد عبد الله حسن", "أبو بكر محمد عبد الله"),
        ("ابو العلا سيد أحمد", "ابو العلا سيد أحمد"),
        ("أحمد محمد علي حسن السيد", "أحمد محمد علي"),
        ("  مريم   أحمد  ", "مريم أحمد"),
        ("محمد عبد", "محمد عبد"),  # trailing "عبد" with nothing to join
        ("", ""),
    ],
)
def test_triple_name(full, expected):
    assert triple_name(full) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("القاهرة", "القاهرة"),
        ("القاهره", "القاهرة"),
        ("محافظة الجيزة", "الجيزة"),
        ("الاسكندريه", "الإسكندرية"),
        ("مدينة نصر - القاهرة", "القاهرة"),
        ("بورسعيد", "بورسعيد"),
        ("باريس", None),
        ("", None),
    ],
)
def test_map_governorate(text, expected):
    assert map_governorate(text) == expected


@pytest.mark.parametrize(
    ("text", "mapping", "expected"),
    [
        ("ذكر", GENDER_VALUES, "MALE"),
        ("انثى", GENDER_VALUES, "FEMALE"),
        ("أنثى", GENDER_VALUES, "FEMALE"),
        ("مسلم", RELIGION_VALUES, "MUSLIM"),
        ("مسلمة", RELIGION_VALUES, "MUSLIM"),
        ("مسيحى", RELIGION_VALUES, "CHRISTIAN"),
        ("طبيب بشري", SYNDICATE_TYPE_VALUES, "HUMAN_MEDICINE"),
        ("صيدلى", SYNDICATE_TYPE_VALUES, "PHARMACY"),
        ("طب الأسنان", SYNDICATE_TYPE_VALUES, "DENTISTRY"),
        ("بيطري", SYNDICATE_TYPE_VALUES, "VETERINARY"),
        ("غير معروف", GENDER_VALUES, None),
        ("", RELIGION_VALUES, None),
    ],
)
def test_map_enum(text, mapping, expected):
    assert map_enum(text, mapping) == expected
