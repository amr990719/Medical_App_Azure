"""No recipient address or message text may reach a log record, however the provider fails."""

import io
import logging

import pytest
from django.utils import timezone
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from apps.notifications import sender
from apps.notifications.factories import NotificationFactory
from apps.notifications.providers import (
    PermanentProviderError,
    TemporaryProviderError,
    UnknownResultError,
    get_email_client,
    get_whatsapp_client,
)
from config.logging import JsonFormatter, NationalIdMaskingFilter
from config.telemetry import MaskingLogRecordProcessor, MaskingSpanProcessor, TelemetryLogHandler

pytestmark = pytest.mark.django_db

SECRETS = [
    "ahmed@example.test",
    "010 1234 5678",
    "+201012345678",
    "٠١٠١٢٣٤٥٦٧٨",
    "نص الرسالة",
]

FAILURES = {
    "permanent": PermanentProviderError,
    "temporary": TemporaryProviderError,
    "unknown": UnknownResultError,
    "plain": Exception,
}


def _string_values(record: logging.LogRecord):
    yield record.getMessage()
    yield record.exc_text or ""
    for value in vars(record).values():
        if isinstance(value, str):
            yield value


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("secret", SECRETS)
def test_seeded_values_never_reach_logs(
    caplog, django_capture_on_commit_callbacks, settings, secret, failure
):
    settings.NOTIFICATIONS_MODE = "live"
    row = NotificationFactory(application__doctor__whatsapp_opt_in=True)
    get_whatsapp_client().errors = [FAILURES[failure](secret)]

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(NationalIdMaskingFilter())
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with (
            caplog.at_level(logging.DEBUG),
            django_capture_on_commit_callbacks(execute=True),
        ):
            sender.run_once(now=timezone.now())
    finally:
        root.removeHandler(handler)

    assert caplog.records
    for record in caplog.records:
        for text in _string_values(record):
            assert secret not in text
    assert secret not in stream.getvalue()
    row.refresh_from_db()
    assert secret not in row.error_code
    if failure in ("permanent", "plain"):  # FAILED rows log a warning with ID and code
        warned = [r for r in caplog.records if getattr(r, "notification_id", None) == str(row.pk)]
        assert any(getattr(r, "error_code", "") for r in warned)
    assert get_email_client().sent == []


def test_a_provider_code_that_is_not_a_code_is_not_logged_or_stored(
    caplog, django_capture_on_commit_callbacks, settings
):
    settings.NOTIFICATIONS_MODE = "live"
    row = NotificationFactory(application__doctor__whatsapp_opt_in=True)
    get_whatsapp_client().errors = [PermanentProviderError("ahmed@example.test")]
    with caplog.at_level(logging.DEBUG), django_capture_on_commit_callbacks(execute=True):
        sender.run_once(now=timezone.now())
    row.refresh_from_db()
    assert row.error_code == sender.SEND_ERROR
    codes = {getattr(r, "error_code", None) for r in caplog.records}
    assert sender.SEND_ERROR in codes


def test_span_and_log_attributes_are_masked():
    secret = "ahmed@example.test"
    phone = "010 1234 5678"

    logs = InMemoryLogRecordExporter()
    log_provider = LoggerProvider()
    log_provider.add_log_record_processor(MaskingLogRecordProcessor())
    log_provider.add_log_record_processor(SimpleLogRecordProcessor(logs))
    logger = logging.getLogger("test.privacy.telemetry")
    handler = TelemetryLogHandler(logger_provider=log_provider)
    logger.addHandler(handler)
    try:
        logger.warning("to %s", secret, extra={"recipient": phone})
    finally:
        logger.removeHandler(handler)
    (exported,) = logs.get_finished_logs()
    dumped = str(exported.log_record.body) + str(dict(exported.log_record.attributes))
    assert secret not in dumped and phone not in dumped

    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(MaskingSpanProcessor())
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    with tracer_provider.get_tracer("test").start_as_current_span(f"send {secret}") as span:
        span.set_attribute("messaging.destination", phone)
        span.record_exception(ValueError(f"rejected {secret}"))
    (finished,) = spans.get_finished_spans()
    dumped = finished.name + str(dict(finished.attributes))
    dumped += "".join(str(dict(e.attributes)) for e in finished.events)
    assert secret not in dumped and phone not in dumped
