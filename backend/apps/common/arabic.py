"""Arabic text helpers: name comparison (validation rule 15) and Egyptian mobile numbers."""

import re

from apps.reference.digits import normalize_digits

# Tashkeel (U+064B..U+0652, incl. shadda U+0651), superscript alef (U+0670), tatweel (U+0640).
_DIACRITICS = re.compile("[ً-ْٰـ]")
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})

MOBILE_RE = re.compile(r"^(\+20|0020|0)?1[0125]\d{8}$")
_PHONE_SEPARATORS = re.compile(r"[\s\-().]+")


def normalize_arabic_name(name: str | None) -> str:
    """Trim, collapse spaces, drop diacritics/tatweel, unify أ/إ/آ→ا, ة→ه, ى→ي."""
    text = _DIACRITICS.sub("", name or "").translate(_LETTERS)
    return " ".join(text.split())


def normalize_mobile(raw: str | None) -> str | None:
    """Canonical local form `01XXXXXXXXX`, or None when the number is not a valid mobile."""
    value = _PHONE_SEPARATORS.sub("", normalize_digits(raw or ""))
    if not MOBILE_RE.fullmatch(value):
        return None
    return "0" + value[-10:]


def is_valid_mobile(raw: str | None) -> bool:
    return normalize_mobile(raw) is not None
