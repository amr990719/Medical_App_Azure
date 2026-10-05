"""Test-only helpers shared by factories and tests."""

from datetime import date

from apps.reference.constants import Gender


def fake_national_id(
    born: date, gender: Gender | str, *, serial: int = 0, governorate: str = "01"
) -> str:
    """Build a structurally valid Egyptian national ID (check digit is arbitrary)."""
    century = "2" if born.year < 2000 else "3"
    gender_digit = (serial % 5) * 2 + (1 if Gender(gender) == Gender.MALE else 0)
    return f"{century}{born:%y%m%d}{governorate}{serial // 5 % 1000:03d}{gender_digit}1"
