"""Application Insights via the Azure Monitor OpenTelemetry distro (PROMPT.md §38, plan 7.5).

`configure_azure_monitor` is mocked (no exporter, no network); the masking processors run inside
real OpenTelemetry SDK providers with in-memory exporters. Export to a real Application Insights
resource is NOT VERIFIED — requires Azure credentials.
"""

import logging
from unittest import mock

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from config import telemetry
from config.logging import NationalIdMaskingFilter

NID = "29501150101234"
MASKED = "29•••••••••234"
CONNECTION = "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://example.invalid/"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("APPLICATIONINSIGHTS_AUTHENTICATION", raising=False)
    monkeypatch.setattr(telemetry, "_configured", False)


def test_disabled_without_connection_string():
    with mock.patch("azure.monitor.opentelemetry.configure_azure_monitor") as configure:
        assert telemetry.configure_telemetry() is False
    configure.assert_not_called()


def test_configures_azure_monitor_with_masking_processors(monkeypatch):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", CONNECTION)
    with (
        mock.patch("azure.monitor.opentelemetry.configure_azure_monitor") as configure,
        mock.patch.object(telemetry, "_instrument_psycopg") as psycopg,
    ):
        assert telemetry.configure_telemetry() is True
        assert telemetry.configure_telemetry() is True  # idempotent
    configure.assert_called_once()
    kwargs = configure.call_args.kwargs
    assert kwargs["connection_string"] == CONNECTION
    assert any(isinstance(p, telemetry.MaskingSpanProcessor) for p in kwargs["span_processors"])
    assert any(
        isinstance(p, telemetry.MaskingLogRecordProcessor) for p in kwargs["log_record_processors"]
    )
    # The distro's own handler goes to a dedicated logger; Django's LOGGING attaches ours (with
    # the masking filter) to the root logger.
    assert kwargs["logger_name"] == telemetry.DISTRO_LOGGER_NAME
    assert "credential" not in kwargs
    psycopg.assert_called_once()


def test_entra_ingestion_uses_the_managed_identity(monkeypatch):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", CONNECTION)
    monkeypatch.setenv("APPLICATIONINSIGHTS_AUTHENTICATION", "entra")
    credential = object()
    with (
        mock.patch("azure.monitor.opentelemetry.configure_azure_monitor") as configure,
        mock.patch.object(telemetry, "_instrument_psycopg"),
        mock.patch("config.azure.get_azure_credential", return_value=credential),
    ):
        telemetry.configure_telemetry()
    assert configure.call_args.kwargs["credential"] is credential


def test_log_record_processor_masks_body_and_attributes():
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(telemetry.MaskingLogRecordProcessor())
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = telemetry.TelemetryLogHandler(logger_provider=provider)
    logger = logging.getLogger("test.telemetry.processor")
    logger.addHandler(handler)
    try:
        try:
            raise ValueError(f"duplicate national id {NID}")
        except ValueError:
            logger.exception("lookup %s failed", NID, extra={"nid": NID})
    finally:
        logger.removeHandler(handler)
    (exported,) = exporter.get_finished_logs()
    record = exported.log_record
    assert NID not in str(record.body)
    assert MASKED in str(record.body)
    for value in record.attributes.values():
        assert NID not in str(value)
    assert any(MASKED in str(v) for v in record.attributes.values())


def test_handler_from_logging_config_masks_through_the_filter():
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = telemetry.TelemetryLogHandler(logger_provider=provider)
    handler.addFilter(NationalIdMaskingFilter())
    logger = logging.getLogger("test.telemetry.filter")
    logger.addHandler(handler)
    try:
        logger.warning("search for %s", NID)
    finally:
        logger.removeHandler(handler)
    (exported,) = exporter.get_finished_logs()
    assert exported.log_record.body == f"search for {MASKED}"


def test_handler_without_a_configured_provider_is_inert():
    handler = telemetry.TelemetryLogHandler()
    handler.handle(logging.makeLogRecord({"msg": NID}))  # no exception, nothing exported


def test_span_processor_masks_attributes_and_exception_events():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(telemetry.MaskingSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("GET /api/v1/admin/applications/") as span:
        span.set_attribute("url.query", f"search={NID}")
        span.set_attribute("http.target", f"/api/v1/admin/applications/?search={NID}")
        span.set_attribute("http.status_code", 200)
        span.record_exception(ValueError(f"Key (national_id)=({NID}) already exists."))
    (finished,) = exporter.get_finished_spans()
    assert finished.attributes["url.query"] == f"search={MASKED}"
    assert finished.attributes["http.target"].endswith(MASKED)
    assert finished.attributes["http.status_code"] == 200
    (event,) = finished.events
    for value in event.attributes.values():
        assert NID not in str(value)
    assert NID not in finished.name


def test_production_logging_routes_to_application_insights_with_the_filter(monkeypatch):
    from config.tests.test_production_settings import load_production

    prod = load_production(monkeypatch, APPLICATIONINSIGHTS_CONNECTION_STRING=CONNECTION)
    handler = prod.LOGGING["handlers"]["telemetry"]
    assert handler["()"] == "config.telemetry.TelemetryLogHandler"
    assert handler["filters"] == ["mask_national_ids"]
    assert "telemetry" in prod.LOGGING["root"]["handlers"]


def test_production_logging_without_application_insights(monkeypatch):
    from config.tests.test_production_settings import load_production

    prod = load_production(monkeypatch, APPLICATIONINSIGHTS_CONNECTION_STRING=None)
    assert "telemetry" not in prod.LOGGING["handlers"]


def test_wsgi_configures_telemetry_before_loading_django():
    from pathlib import Path

    source = (Path(telemetry.__file__).parent / "wsgi.py").read_text(encoding="utf-8")
    assert source.index("configure_telemetry()") < source.index("get_wsgi_application()")
