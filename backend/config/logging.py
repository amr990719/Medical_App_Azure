"""Structured JSON logging with national-ID masking (PROMPT.md §38).

`NationalIdMaskingFilter` rewrites every record so no run of 11+ digits (Western or Eastern
Arabic: national IDs and phone numbers), no Egyptian mobile written with spaces or hyphens and no
e-mail address survives; `JsonFormatter` masks its final output again, which also covers exception
tracebacks and `extra` fields formatted after the filter ran.
"""

import json
import logging
import re
from datetime import UTC, datetime

_DIGIT_RUN = re.compile(r"\d{11,}")  # str pattern: \d also matches Arabic-Indic digits
# Egyptian mobile (+20 / 20 / 0, then 1[0125], then 8 digits) with optional spaces or hyphens
# between digits. Matching the shape keeps dates, UUIDs and ordinary numbers untouched.
_MOBILE = re.compile(r"(?<![\d+])(?:\+?(?:20|٢٠)|[0٠])[1١][0125٠١٢٥](?:[\s-]?\d){8}(?!\d)")
_EMAIL = re.compile(r"[^\s@\"']+@[^\s@\"']+")
MASK_CHAR = "•"
EMAIL_MASK = "[email]"

# Attributes every LogRecord has; anything else came from `extra=`.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _mask(match: re.Match) -> str:
    run = match.group(0)
    return run[:2] + MASK_CHAR * (len(run) - 5) + run[-3:]


def mask_digit_runs(text: str) -> str:
    text = _EMAIL.sub(EMAIL_MASK, text)
    text = _DIGIT_RUN.sub(_mask, text)
    return _MOBILE.sub(_mask, text)


class NationalIdMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_digit_runs(record.getMessage())
        record.args = None
        for key, value in vars(record).items():
            if key not in _RESERVED and isinstance(value, str):
                setattr(record, key, mask_digit_runs(value))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {k: v for k, v in vars(record).items() if k not in _RESERVED and not k.startswith("_")}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return mask_digit_runs(json.dumps(payload, ensure_ascii=False, default=str))
