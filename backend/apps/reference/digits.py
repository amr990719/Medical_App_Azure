"""Digit normalization. Eastern Arabic digits are accepted everywhere and never dropped."""

_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)


def normalize_digits(text: str | None) -> str:
    """Map Eastern Arabic (U+0660..) and Persian (U+06F0..) digits to ASCII 0-9."""
    if not text:
        return ""
    return text.translate(_TRANSLATION)
