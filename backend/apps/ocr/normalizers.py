"""Normalizers for raw OCR output (PROMPT.md §21.4), ported from the prototype's OcrService.js.

OCR only SUGGESTS: anything implausible becomes "no suggestion" (empty / None) rather than a
wrong value the doctor might not notice.
"""

import difflib
import re

from apps.common.arabic import normalize_arabic_name
from apps.reference.constants import GOVERNORATES
from apps.reference.digits import normalize_digits

_YEAR = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
_NAME_PREFIXES = frozenset({"عبد", "أبو", "ابو"})
_GOVERNORATE_NOISE = re.compile(r"^(محافظه|محافظة)\s+")
GOVERNORATE_MATCH_CUTOFF = 0.8

GENDER_VALUES = {"MALE": ("ذكر",), "FEMALE": ("انثي",)}
RELIGION_VALUES = {"MUSLIM": ("مسلم",), "CHRISTIAN": ("مسيحي",)}
SYNDICATE_TYPE_VALUES = {
    "HUMAN_MEDICINE": ("بشري",),
    "PHARMACY": ("صيدلي",),
    "DENTISTRY": ("اسنان",),
    "VETERINARY": ("بيطري",),
}


def clean_text(raw) -> str:
    return " ".join(normalize_digits(str(raw or "")).split())


def clean_national_id(raw) -> str:
    """Digits only (Eastern Arabic normalized); the first 14 of them, or "" if fewer."""
    digits = digits_only(raw)
    return digits[:14] if len(digits) >= 14 else ""


def birth_year_from_id(id14: str) -> int | None:
    """`2` → 19YY, `3` → 20YY."""
    if not re.fullmatch(r"[0-9]{14}", id14 or ""):
        return None
    century = {"2": 1900, "3": 2000}.get(id14[0])
    return century + int(id14[1:3]) if century else None


def extract_year(raw) -> int | None:
    """First 19xx/20xx year in a date text (any order, any separator, Arabic digits); else the
    first four digits when they form a plausible year."""
    text = normalize_digits(str(raw or ""))
    match = _YEAR.search(text)
    if match:
        return int(match.group(0))
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) >= 4 and 1900 <= int(digits[:4]) <= 2099:
        return int(digits[:4])
    return None


def digits_only(raw) -> str:
    return re.sub(r"[^0-9]", "", normalize_digits(str(raw or "")))


def triple_name(full) -> str:
    """First three names; `عبد` / `أبو` / `ابو` are joined with the following word."""
    words = str(full or "").split()
    names: list[str] = []
    i = 0
    while i < len(words):
        if words[i] in _NAME_PREFIXES and i + 1 < len(words):
            names.append(f"{words[i]} {words[i + 1]}")
            i += 2
        else:
            names.append(words[i])
            i += 1
    return " ".join(names[:3])


_NORMALIZED_GOVERNORATES = {normalize_arabic_name(g): g for g in GOVERNORATES}


def map_governorate(text) -> str | None:
    """Closest of the 27 residence governorates, or None. Tries the whole text, then each part
    of an `area - governorate` line."""
    cleaned = normalize_arabic_name(clean_text(text))
    if not cleaned:
        return None
    candidates = [cleaned, *(p.strip() for p in re.split(r"[-–—/،,]", cleaned))]
    for candidate in candidates:
        candidate = _GOVERNORATE_NOISE.sub("", candidate)
        if candidate in _NORMALIZED_GOVERNORATES:
            return _NORMALIZED_GOVERNORATES[candidate]
        close = difflib.get_close_matches(
            candidate, _NORMALIZED_GOVERNORATES, n=1, cutoff=GOVERNORATE_MATCH_CUTOFF
        )
        if close:
            return _NORMALIZED_GOVERNORATES[close[0]]
    return None


def map_enum(text, mapping: dict[str, tuple[str, ...]]) -> str | None:
    """Enum value whose normalized keyword appears in the text (`طبيب بشري` → HUMAN_MEDICINE)."""
    cleaned = normalize_arabic_name(clean_text(text))
    if not cleaned:
        return None
    for value, keywords in mapping.items():
        if any(keyword in cleaned for keyword in keywords):
            return value
    return None
