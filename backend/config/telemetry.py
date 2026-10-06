"""OpenTelemetry → Application Insights (PROMPT.md §38) through the Azure Monitor distro.

`configure_telemetry()` runs in `config/wsgi.py` in every Gunicorn worker (no `--preload`, so
after the fork) BEFORE Django loads, so the Django middleware instrumentation is in place;
it is a no-op without `APPLICATIONINSIGHTS_CONNECTION_STRING` (local development, tests,
management commands). Requests, dependencies (psycopg, requests/httpx, Azure SDK) and
exceptions are exported.

National IDs must never reach Application Insights, so masking happens at three points:
- logs: Django's LOGGING attaches `TelemetryLogHandler` to the root logger WITH the
  `NationalIdMaskingFilter` (the distro's own handler is parked on `DISTRO_LOGGER_NAME`; Django's
  dictConfig would remove it from the root logger anyway);
- `MaskingLogRecordProcessor` re-masks the body and every string attribute (exception messages
  and stack traces are attributes) before the exporter sees the record;
- `MaskingSpanProcessor` drops query strings and fragments from URL attributes (`url.query`,
  `url.full`, `http.url`, `http.target`: search terms, phone numbers, e-mails, OIDC `code`/`state`
  — the access log never records them either) and masks span names, string attributes and
  exception events before the batch exporter receives the span.
Ingestion uses the connection string; `APPLICATIONINSIGHTS_AUTHENTICATION=entra` adds the managed
identity (`Monitoring Metrics Publisher` role) for Entra-authenticated ingestion.
NOT VERIFIED against a real Application Insights resource — requires Azure credentials.
"""

import logging
import os

from opentelemetry.sdk._logs import LogRecordProcessor, ReadWriteLogRecord
from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor

from config.logging import mask_digit_runs

DISTRO_LOGGER_NAME = "config.telemetry.distro"
# Span attributes holding a URL (old and new HTTP semantic conventions) and the query itself.
URL_ATTRIBUTES = frozenset({"url.full", "http.url", "http.target"})
DROPPED_ATTRIBUTES = frozenset({"url.query", "url.fragment"})
# Header capture is off by default (OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_*); if someone turns
# it on, credentials still never leave the process.
CREDENTIAL_HEADERS = ("cookie", "set_cookie", "set-cookie", "authorization", "csrftoken", "api_key")
SERVICE_NAME = "medical-syndicates-backend"

_configured = False


def _mask_value(value):
    if isinstance(value, str):
        return mask_digit_runs(value)
    if isinstance(value, tuple | list):
        return type(value)(_mask_value(v) for v in value)
    return value


def _without_query(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def _span_attributes(attributes) -> dict:
    cleaned = {}
    for key, value in (attributes or {}).items():
        if key in DROPPED_ATTRIBUTES or (
            ".header." in key and any(h in key.lower() for h in CREDENTIAL_HEADERS)
        ):
            continue
        if key in URL_ATTRIBUTES and isinstance(value, str):
            value = _without_query(value)
        cleaned[key] = _mask_value(value)
    return cleaned


def _mask_mapping(attributes) -> dict:
    return {key: _mask_value(value) for key, value in (attributes or {}).items()}


class MaskingLogRecordProcessor(LogRecordProcessor):
    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        record = log_record.log_record
        record.body = _mask_value(record.body)
        if record.attributes:
            for key, value in list(record.attributes.items()):
                masked = _mask_value(value)
                if masked != value:
                    record.attributes[key] = masked

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class MaskingSpanProcessor(SpanProcessor):
    """Runs before the exporter's batch processor (the distro registers custom processors
    first) and rewrites the finished span it is handed, which is the object exported next."""

    def on_end(self, span: ReadableSpan) -> None:
        span._name = mask_digit_runs(_without_query(span._name))
        span._attributes = _span_attributes(span._attributes)
        span._events = tuple(
            Event(event.name, _mask_mapping(event.attributes), event.timestamp)
            for event in span._events
        )


class TelemetryLogHandler(logging.Handler):
    """Root-logger handler (from Django LOGGING) forwarding to the OpenTelemetry logger provider
    configured by the distro. Inert when telemetry is not configured."""

    def __init__(self, level=logging.NOTSET, logger_provider=None) -> None:
        super().__init__(level)
        from opentelemetry._logs import get_logger_provider
        from opentelemetry.instrumentation.logging.handler import LoggingHandler
        from opentelemetry.sdk._logs import LoggerProvider

        provider = logger_provider or get_logger_provider()
        self._delegate = (
            LoggingHandler(logger_provider=provider)
            if isinstance(provider, LoggerProvider)
            else None
        )

    def emit(self, record: logging.LogRecord) -> None:
        if self._delegate is not None:
            self._delegate.emit(record)

    def flush(self) -> None:
        if self._delegate is not None:
            self._delegate.flush()


def _instrument_psycopg() -> None:
    # The distro instruments psycopg2 only; this project uses psycopg 3.
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    PsycopgInstrumentor().instrument(enable_commenter=False)


def configure_telemetry() -> bool:
    global _configured
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
    if not connection_string:
        return False
    if _configured:
        return True

    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.sdk.resources import SERVICE_NAME as SERVICE_NAME_KEY
    from opentelemetry.sdk.resources import Resource

    options = {
        "connection_string": connection_string,
        "resource": Resource.create(
            {SERVICE_NAME_KEY: os.environ.get("OTEL_SERVICE_NAME", SERVICE_NAME)}
        ),
        "span_processors": [MaskingSpanProcessor()],
        "log_record_processors": [MaskingLogRecordProcessor()],
        "logger_name": DISTRO_LOGGER_NAME,
        "instrumentation_options": {"flask": {"enabled": False}, "fastapi": {"enabled": False}},
    }
    if os.environ.get("APPLICATIONINSIGHTS_AUTHENTICATION", "").lower() == "entra":
        from config.azure import get_azure_credential

        options["credential"] = get_azure_credential()
    configure_azure_monitor(**options)
    _instrument_psycopg()
    _configured = True
    return True
