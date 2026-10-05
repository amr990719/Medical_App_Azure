import pytest

from apps.common.arabic import is_valid_mobile, normalize_arabic_name, normalize_mobile


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("أحمد محمّد علي", "احمد محمد علي"),  # hamza forms + shadda
        ("إيمان", "ايمان"),
        ("آمنة", "امنه"),  # alef madda and taa marbuta
        ("مصطفى", "مصطفي"),  # alef maqsura
        ("  أحمد   محمد  ", "احمد محمد"),  # trim and collapse spaces
        ("محـــمد", "محمد"),  # tatweel
        ("مُحَمَّد", "محمد"),  # full tashkeel
    ],
)
def test_names_normalize_to_the_same_form(a, b):
    assert normalize_arabic_name(a) == normalize_arabic_name(b)


def test_different_names_stay_different():
    assert normalize_arabic_name("أحمد علي") != normalize_arabic_name("أحمد عمر")


def test_normalize_empty_name():
    assert normalize_arabic_name(None) == ""
    assert normalize_arabic_name("   ") == ""


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("01012345678", "01012345678"),
        ("+201012345678", "01012345678"),
        ("00201112345678", "01112345678"),
        ("1212345678", "01212345678"),
        ("٠١٥١٢٣٤٥٦٧٨", "01512345678"),  # Eastern Arabic digits
        ("010 1234 5678", "01012345678"),
        ("010-1234-5678", "01012345678"),
    ],
)
def test_normalize_mobile(raw, canonical):
    assert normalize_mobile(raw) == canonical
    assert is_valid_mobile(raw) is True


@pytest.mark.parametrize("raw", ["", None, "01312345678", "0101234567", "021234567", "abc"])
def test_invalid_mobile(raw):
    assert normalize_mobile(raw) is None
    assert is_valid_mobile(raw) is False
