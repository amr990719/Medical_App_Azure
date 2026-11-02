"""Inbound WhatsApp messages (spec section 7): stop requests and the once-a-day help reply.

The text and the sender are used here and nowhere else: neither is logged or stored.
"""

import string
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from apps.common.arabic import normalize_arabic_name
from apps.doctors import services as doctor_services

from .formatting import from_whatsapp_sender, to_e164
from .templates import HELP_REPLY, STOP_CONFIRMATION

STOP_WORDS = frozenset({"ايقاف", "stop"})
_TRIM = string.punctuation + string.whitespace + "،؛؟…"


@dataclass(frozen=True)
class Reply:
    to: str = field(repr=False)  # full number, in memory only
    body: str


def is_stop_word(text: str) -> bool:
    """The whole text, trimmed of spaces and punctuation and ignoring case, is a stop word."""
    return normalize_arabic_name(text.strip(_TRIM)).casefold() in STOP_WORDS


def _message_time(message: dict, now: datetime) -> datetime:
    """Meta's `timestamp` (epoch seconds, as a string); anything unusable counts as now."""
    raw = message.get("timestamp")
    if isinstance(raw, str) and raw.isascii() and raw.isdecimal():
        try:
            return datetime.fromtimestamp(int(raw), tz=UTC)
        except (OverflowError, OSError, ValueError):
            pass
    return now


def _stop_text(message: dict) -> str | None:
    if message.get("type") != "text":
        return None
    text: Any = message.get("text")
    body = text.get("body") if isinstance(text, dict) else None
    return body if isinstance(body, str) else None


def handle_message(message: dict, *, now: datetime) -> Reply | None:
    """Apply a stop or claim a help reply for one inbound message. Sending is the caller's job,
    after the commit. Anything malformed, foreign or unknown gets no action and no reply."""
    sender = message.get("from")
    local = from_whatsapp_sender(sender) if isinstance(sender, str) else None
    if local is None:
        return None
    text = _stop_text(message)
    if text is not None and is_stop_word(text):
        changed = doctor_services.stop_whatsapp_for_number(
            local, message_time=_message_time(message, now)
        )
        return Reply(to=to_e164(local), body=STOP_CONFIRMATION) if changed else None
    if doctor_services.claim_help_reply(local, now=now):
        return Reply(to=to_e164(local), body=HELP_REPLY)
    return None
