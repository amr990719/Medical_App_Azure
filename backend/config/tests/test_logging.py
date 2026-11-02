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


def test_ordinary_numbers_are_untouched():
    assert mask_digit_runs("year 2026, total 3025") == "year 2026, total 3025"


def test_dates_and_uuids_are_untouched():
    text = "2026-11-02 10:30:15 8f14e45f-ceea-467f-a0f2-1a2b3c4d5e6f"
    assert mask_digit_runs(text) == text


@pytest.mark.parametrize(
    "uuid_text",
    [
        "8f14e45f-ceea-467f-a0f2-123456789012",  # all-digit last group
        "00000000-0000-4000-8000-000000000000",
        "8F14E45F-CEEA-467F-A0F2-123456789012",
    ],
)
def test_canonical_uuids_are_never_masked(uuid_text):
    assert mask_digit_runs(f"notification_id={uuid_text} ok") == f"notification_id={uuid_text} ok"


def test_a_national_id_next_to_a_uuid_is_still_masked():
    text = f"{NID} 8f14e45f-ceea-467f-a0f2-123456789012"
    assert NID not in mask_digit_runs(text)
    assert NID not in mask_digit_runs(f"{NID}8f14e45f-ceea-467f-a0f2-123456789012")


def test_django_request_object_is_not_in_the_json_payload(capture):
    logger, stream = capture

    class FakeRequest:
        def __str__(self):
            return "<WSGIRequest: GET '/hook/?hub.verify_token=s3cret'>"

    logger.warning("Forbidden: /hook/", extra={"request": FakeRequest(), "status_code": 403})
    assert "s3cret" not in stream.getvalue()
    assert "request" not in output(stream)
    assert output(stream)["status_code"] == 403


@pytest.mark.parametrize(
    "phone",
    [
        "01012345678",
        "201012345678",
        "+201012345678",
        "010 1234 5678",
        "010-1234-5678",
        "٠١٠١٢٣٤٥٦٧٨",
        "+20 10 1234 5678",
        "+20 1012345678",
        "20-10-1234-5678",
        "+20-101-234-5678",
        "+٢٠ ١٠ ١٢٣٤ ٥٦٧٨",
    ],
)
def test_phones_are_masked(phone):
    assert phone not in mask_digit_runs(f"to {phone}")


def test_emails_are_masked():
    assert "ahmed@example.com" not in mask_digit_runs("to ahmed@example.com")


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
