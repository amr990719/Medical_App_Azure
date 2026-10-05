import io
import json
import logging

import pytest

from config.logging import JsonFormatter, NationalIdMaskingFilter, mask_digit_runs

NID = "29501230101234"


@pytest.fixture
def capture():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(NationalIdMaskingFilter())
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.masking")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield logger, stream
    logger.handlers = []


def output(stream):
    return json.loads(stream.getvalue().strip().splitlines()[-1])


def test_filter_masks_14_digit_runs():
    assert mask_digit_runs(f"id {NID} ok") == "id 29•••••••••234 ok"


def test_filter_masks_eastern_arabic_digit_runs():
    assert "٢٩٥٠١٢٣٠١٠١٢٣٤" not in mask_digit_runs("رقم ٢٩٥٠١٢٣٠١٠١٢٣٤")


def test_shorter_numbers_are_untouched():
    assert mask_digit_runs("year 2026, total 3025, phone 01012345678") == (
        "year 2026, total 3025, phone 01012345678"
    )


def test_message_arguments_are_masked(capture):
    logger, stream = capture
    logger.info("doctor %s submitted", NID)
    record = output(stream)
    assert NID not in stream.getvalue()
    assert record["message"] == "doctor 29•••••••••234 submitted"


def test_exception_text_is_masked(capture):
    logger, stream = capture
    try:
        raise ValueError(f"bad id {NID}")
    except ValueError:
        logger.exception("failed")
    assert NID not in stream.getvalue()
    assert "29•••••••••234" in output(stream)["exception"]


def test_extra_fields_are_masked(capture):
    logger, stream = capture
    logger.info("lookup", extra={"query": f"national_id={NID}"})
    assert NID not in stream.getvalue()


def test_json_formatter_fields(capture):
    logger, stream = capture
    logger.warning("hello", extra={"request_id": "abc", "user_id": "u-1", "status": 200})
    record = output(stream)
    assert record["level"] == "WARNING"
    assert record["logger"] == "test.masking"
    assert record["message"] == "hello"
    assert record["request_id"] == "abc"
    assert record["user_id"] == "u-1"
    assert record["status"] == 200
    assert "timestamp" in record


def test_project_logging_uses_the_masking_filter():
    handler = logging.getLogger().handlers[0]
    assert any(isinstance(f, NationalIdMaskingFilter) for f in handler.filters)
    assert isinstance(handler.formatter, JsonFormatter)
