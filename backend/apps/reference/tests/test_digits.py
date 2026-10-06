import pytest

from apps.reference.digits import normalize_digits


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("٠١٢٣٤٥٦٧٨٩", "0123456789"),  # Eastern Arabic (U+0660..)
        ("۰۱۲۳۴۵۶۷۸۹", "0123456789"),  # Extended Arabic-Indic / Persian (U+06F0..)
        ("سنة ٢٠٢٦", "سنة 2026"),
        ("abc 123", "abc 123"),
        ("", ""),
    ],
)
def test_normalize_digits(raw, expected):
    assert normalize_digits(raw) == expected


def test_normalize_digits_accepts_none():
    assert normalize_digits(None) == ""
