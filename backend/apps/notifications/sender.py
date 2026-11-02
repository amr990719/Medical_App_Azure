"""One run of the notification job (spec section 6): sweep old rows, then send the due ones.

Provider calls happen here, outside any database transaction. Each claimed row ends with exactly
one `record_*` call. Logs carry notification IDs, codes and counts only, never an address, a
message or a traceback (a traceback could hold a recipient).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from apps.reference.constants import NotificationChannel

from . import services
from .formatting import SEND_ERROR, safe_code, to_e164
from .providers import (
    PermanentProviderError,
    TemporaryProviderError,
    UnknownResultError,
    get_email_client,
    get_whatsapp_client,
)
from .services import Claim
from .templates import MESSAGES, render_email, template_parameters

logger = logging.getLogger("apps.notifications")

MAX_ROWS = 200
BUDGET_SECONDS = 240
MIN_REMAINING_SECONDS = 15
OUTAGE_STREAK = 5
NO_ADDRESS = "NO_ADDRESS"
SENDING_MODES = frozenset({"allowlist", "live"})

# What an attempt says about the provider: OK (it answered: success, or a permanent WhatsApp
# rejection) resets the outage streak, ERROR (temporary, unknown or an unexpected fault) adds one, and KEEP
# (the row never reached a provider) leaves it alone.
OK, ERROR, KEEP = "ok", "error", "keep"


@dataclass
class RunSummary:
    expired: int = 0
    recovered: int = 0
    timed_out: int = 0
    attempted: int = 0
    sent: int = 0
    retried: int = 0
    failed: int = 0
    unknown: int = 0
    skipped_channels: int = 0
    oldest_due_age_seconds: int | None = None


def _send_whatsapp(claim: Claim) -> str:
    return get_whatsapp_client().send_template(
        to=to_e164(claim.recipient),
        template=MESSAGES[claim.event].meta_name,
        parameters=template_parameters(
            claim.event, reference=claim.reference_number, amount=claim.amount
        ),
    )


def _send_email(claim: Claim) -> str:
    message = render_email(claim.event, reference=claim.reference_number, amount=claim.amount)
    return get_email_client().send(
        to=claim.recipient, subject=message.subject, html=message.html, text=message.text
    )


def _attempt(claim: Claim, *, now: datetime, summary: RunSummary) -> str:
    """Send one claimed row and record the outcome; OK, ERROR or KEEP says how the streak moves."""
    if not claim.recipient:
        services.record_permanent(claim, error_code=NO_ADDRESS)
        summary.failed += 1
        return KEEP
    try:
        if claim.channel == NotificationChannel.WHATSAPP:
            message_id = _send_whatsapp(claim)
        else:
            message_id = _send_email(claim)
    except TemporaryProviderError as exc:
        services.record_temporary(claim, error_code=safe_code(exc.code), now=now)
        summary.retried += 1
        return ERROR
    except UnknownResultError:
        services.record_unknown(claim, now=now)
        summary.unknown += 1
        return ERROR
    except PermanentProviderError as exc:
        services.record_permanent(claim, error_code=safe_code(exc.code))
        summary.failed += 1
        # WhatsApp rejections still fall back to email, so the provider is fine. Email is the last
        # channel: five rejections in a row look like a systematic fault, so they stop the run.
        return ERROR if claim.channel == NotificationChannel.EMAIL else OK
    except Exception:
        # Notification ID only, no traceback and no message: either could hold the recipient.
        logger.error(
            "notification_send_error", extra={"notification_id": str(claim.notification_id)}
        )
        services.record_permanent(claim, error_code=SEND_ERROR)
        summary.failed += 1
        return ERROR
    services.record_accepted(claim, provider_message_id=message_id)
    summary.sent += 1
    return OK


def _send_channel(
    channel: str,
    *,
    now: datetime,
    summary: RunSummary,
    clock: Callable[[], float],
    started: float,
) -> None:
    streak = 0
    while summary.attempted < MAX_ROWS:
        if BUDGET_SECONDS - (clock() - started) < MIN_REMAINING_SECONDS:
            return
        claim = services.claim_next(channel, now=now)
        if claim is None:
            return
        summary.attempted += 1
        outcome = _attempt(claim, now=now, summary=summary)
        if outcome == OK:
            streak = 0
        elif outcome == ERROR:
            streak += 1
        if streak >= OUTAGE_STREAK:
            summary.skipped_channels += 1
            return


def run_once(
    *, now: datetime | None = None, clock: Callable[[], float] = time.monotonic
) -> RunSummary:
    """Expire, recover, time out, send (email first, then WhatsApp), then log the summary.

    Only `allowlist` and `live` send; any other mode (`off`, or a value nobody recognises)
    runs just the expiry sweep and the summary.
    """
    started = clock()
    now = now or timezone.now()
    summary = RunSummary()
    summary.expired = services.expire_overdue(now=now)
    if settings.NOTIFICATIONS_MODE in SENDING_MODES:
        summary.recovered = services.recover_stuck(now=now)
        summary.timed_out = services.apply_delivery_timeout(now=now)
        for channel in (NotificationChannel.EMAIL, NotificationChannel.WHATSAPP):
            _send_channel(channel, now=now, summary=summary, clock=clock, started=started)
    summary.oldest_due_age_seconds = services.oldest_due_age_seconds(now=now)
    logger.info("notify_run", extra=asdict(summary))
    return summary
