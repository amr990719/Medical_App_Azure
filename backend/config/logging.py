"""Structured JSON logging with national-ID masking (PROMPT.md §38).

`NationalIdMaskingFilter` rewrites every record so no run of 14+ digits (Western or Eastern
Arabic) survives; `JsonFormatter` masks its final output again, which also covers exception
tracebacks and `extra` fields formatted after the filter ran.
"""

import json
import logging
import re
from datetime import UTC, datetime

_DIGIT_RUN = re.compile(r"\d{14,}")  # str pattern: \d also matches Arabic-Indic digits
MASK_CHAR = "•"

# Attributes every LogRecord has; anything else came from `extra=`.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _mask(match: re.Match) -> str:
    run = match.group(0)
    return run[:2] + MASK_CHAR * (len(run) - 5) + run[-3:]


def mask_digit_runs(text: str) -> str:
    return _DIGIT_RUN.sub(_mask, text)


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
