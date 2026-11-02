"""Display and masking helpers for notifications. No provider or database access here."""

from decimal import ROUND_HALF_UP, Decimal

from apps.common.arabic import normalize_mobile
from config.logging import MASK_CHAR

# Same character as `ARABIC_THOUSANDS_SEPARATOR` in frontend/src/utils/format.ts.
ARABIC_THOUSANDS_SEPARATOR = "٬"
CURRENCY = "ج.م"


def format_amount(amount: Decimal) -> str:
    """`Decimal("1250.50")` as `1٬250.50 ج.م`; a zero fraction is dropped. Never uses float."""
    exact = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, fraction = format(exact, "f").partition(".")
    sign = "-" if whole.startswith("-") else ""
    digits = whole.lstrip("-")
    groups: list[str] = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    text = sign + ARABIC_THOUSANDS_SEPARATOR.join(groups)
    if fraction.strip("0"):
        text += f".{fraction}"
    return f"{text} {CURRENCY}"


def to_e164(local: str) -> str:
    """`01XXXXXXXXX` to `+201XXXXXXXXX`."""
    return f"+20{local[1:]}"


def from_whatsapp_sender(raw: str) -> str | None:
    """Meta's sender `2010…` (or `+2010…`) as the stored `010…`, None if not an Egyptian mobile."""
    digits = raw.strip()
    if len(digits) == 12 and digits.startswith("20"):
        digits = f"+{digits}"  # Meta omits the plus; `normalize_mobile` expects it
    return normalize_mobile(digits)


def mask_phone(local: str) -> str:
    """`01012345678` as `010•••••678`."""
    return local[:3] + MASK_CHAR * max(len(local) - 6, 0) + local[-3:]


def mask_email(address: str) -> str:
    """`ahmed@example.com` as `a•••@example.com`."""
    name, at, domain = address.partition("@")
    return name[:1] + MASK_CHAR * 3 + at + domain
