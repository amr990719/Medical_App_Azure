"""Stop and help replies (spec section 7)."""

import hmac
import json
import logging
from datetime import timedelta
from hashlib import sha256

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.notifications import providers
from apps.notifications.factories import NotificationFactory
from apps.notifications.inbound import Reply, handle_message, is_stop_word
from apps.notifications.models import Notification
from apps.notifications.providers import (
    PermanentProviderError,
    TemporaryProviderError,
    UnknownResultError,
)
from apps.notifications.services import claim_next
from apps.notifications.templates import HELP_REPLY, STOP_CONFIRMATION

SECRET = "test-app-secret"  # pinned in config/settings/test.py
PHONE = "01012345678"
SENDER = "201012345678"
pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("text", ["إيقاف", "ايقاف", " إيقاف. ", "stop", "STOP", "Stop!", "إيقاف،"])
def test_stop_words(text):
    assert is_stop_word(text)


@pytest.mark.parametrize("text", ["please stop texting me", "لا تقم بإيقاف الطلب", "", "stopp"])
def test_not_stop_words(text):
    assert not is_stop_word(text)


def text_message(body, sender=SENDER, timestamp=None):
    message = {"from": sender, "type": "text", "text": {"body": body}}
    if timestamp is not None:
        message["timestamp"] = str(timestamp)
    return message


def body_of(*messages, phone_id="111"):
    value = {"metadata": {"phone_number_id": phone_id}, "messages": list(messages)}
    return json.dumps({"entry": [{"changes": [{"value": value}]}]}).encode()


def post(*messages):
    raw = body_of(*messages)
    signature = "sha256=" + hmac.new(SECRET.encode(), raw, sha256).hexdigest()
    return APIClient().generic(
        "POST",
        reverse("whatsapp-webhook"),
        raw,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )


def sent():
    return providers.get_whatsapp_client().sent


def opted_in_doctor(**fields):
    return DoctorFactory(
        phone_number=PHONE, whatsapp_opt_in=True, whatsapp_opt_in_at=timezone.now(), **fields
    )


def failed_codes(caplog):
    return [r.error_code for r in caplog.records if r.getMessage() == "whatsapp_reply_failed"]


def test_stop_clears_opt_in_audits_as_system_and_confirms():
    doctor = opted_in_doctor()
    assert post(text_message("إيقاف")).status_code == 200
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False
    assert doctor.whatsapp_opt_in_at is None
    entry = AuditLog.objects.get(object_id=doctor.pk, action="WHATSAPP_OPT_IN_CHANGED")
    assert entry.user is None
    assert entry.metadata == {"enabled": False, "source": "whatsapp_reply"}
    assert sent() == [{"kind": "text", "to": "+201012345678", "body": STOP_CONFIRMATION}]


def test_two_doctors_sharing_a_number_are_both_stopped():
    first, second = opted_in_doctor(), opted_in_doctor()
    post(text_message("stop"))
    for doctor in (first, second):
        doctor.refresh_from_db()
        assert doctor.whatsapp_opt_in is False
    assert AuditLog.objects.filter(action="WHATSAPP_OPT_IN_CHANGED").count() == 2
    assert len(sent()) == 1


def test_repeated_stop_changes_nothing_and_sends_no_second_reply():
    opted_in_doctor()
    post(text_message("stop"))
    post(text_message("stop"))
    assert len(sent()) == 1
    assert AuditLog.objects.filter(action="WHATSAPP_OPT_IN_CHANGED").count() == 1


def test_old_stop_cannot_undo_a_newer_opt_in():
    doctor = opted_in_doctor()
    old = int((doctor.whatsapp_opt_in_at - timedelta(hours=1)).timestamp())
    post(text_message("stop", timestamp=old))
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True
    assert sent() == []


def test_pending_row_goes_to_email_after_a_stop():
    doctor = opted_in_doctor()
    row = NotificationFactory(channel="WHATSAPP", application__doctor=doctor)
    post(text_message("stop"))
    assert claim_next("WHATSAPP", now=timezone.now()) is None
    row.refresh_from_db()
    assert (row.status, row.error_code) == ("FAILED", "OPTED_OUT")
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()


def test_stop_works_in_off_mode_without_a_reply(settings):
    settings.NOTIFICATIONS_MODE = "off"
    doctor = opted_in_doctor()
    post(text_message("stop"))
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False
    assert sent() == []


def test_allowlist_mode_replies_only_to_listed_numbers(settings):
    settings.NOTIFICATIONS_MODE = "allowlist"
    settings.NOTIFICATIONS_ALLOWLIST = ["+201199999999"]
    doctor = opted_in_doctor()
    post(text_message("stop"))
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False  # applied regardless
    assert sent() == []
    settings.NOTIFICATIONS_ALLOWLIST = ["01012345678"]
    again = opted_in_doctor()
    post(text_message("stop"))
    again.refresh_from_db()
    assert again.whatsapp_opt_in is False
    assert [m["to"] for m in sent()] == ["+201012345678"]


def test_other_text_gets_help_once_in_24_hours():
    doctor = DoctorFactory(phone_number=PHONE)
    post(text_message("مرحبا"))
    assert sent() == [{"kind": "text", "to": "+201012345678", "body": HELP_REPLY}]
    post(text_message("مرحبا"))
    assert len(sent()) == 1
    Doctor.objects.filter(pk=doctor.pk).update(
        whatsapp_help_sent_at=timezone.now() - timedelta(hours=25)
    )
    post(text_message("مرحبا"))
    assert len(sent()) == 2


def test_non_text_message_gets_help_not_stop():
    doctor = opted_in_doctor()
    post({"from": SENDER, "type": "image", "image": {"id": "x"}})
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True
    assert [m["body"] for m in sent()] == [HELP_REPLY]


def test_sentence_containing_stop_gets_help():
    doctor = opted_in_doctor()
    post(text_message("please stop texting me"))
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True
    assert [m["body"] for m in sent()] == [HELP_REPLY]


def test_unknown_number_gets_no_action_and_no_reply():
    post(text_message("stop"))
    post(text_message("hello"))
    assert sent() == []
    assert not AuditLog.objects.filter(action="WHATSAPP_OPT_IN_CHANGED").exists()


def test_incomplete_profile_number_never_matches():
    doctor = DoctorFactory(phone_number="0101", whatsapp_opt_in=True)
    post(text_message("stop"))
    post(text_message("hello"))
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is True
    assert doctor.whatsapp_help_sent_at is None
    assert sent() == []


def test_non_egyptian_sender_is_ignored():
    opted_in_doctor()
    post(text_message("stop", sender="14155550123"))
    assert sent() == []


@pytest.mark.parametrize("bad", ["abc", "99999999999999999999", "", None, 5])
def test_malformed_timestamp_is_treated_as_now(bad):
    doctor = opted_in_doctor()
    message = text_message("stop")
    message["timestamp"] = bad
    post(message)
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False


@pytest.mark.parametrize(
    "error", [TemporaryProviderError("X"), UnknownResultError("Y"), PermanentProviderError("Z")]
)
def test_failed_reply_still_returns_200_and_keeps_the_stop(error, caplog):
    doctor = opted_in_doctor()
    providers.get_whatsapp_client().errors.append(error)
    with caplog.at_level(logging.DEBUG):
        assert post(text_message("stop")).status_code == 200
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False
    assert failed_codes(caplog) == [error.code]
    assert "Traceback" not in caplog.text


def test_unexpected_client_exception_is_a_logged_send_error(caplog):
    doctor = opted_in_doctor()
    providers.get_whatsapp_client().errors.append(RuntimeError("boom +201012345678"))
    with caplog.at_level(logging.DEBUG):
        assert post(text_message("stop")).status_code == 200
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False
    assert failed_codes(caplog) == ["SEND_ERROR"]
    assert "boom" not in caplog.text
    assert "Traceback" not in caplog.text
    assert all(r.exc_info is None for r in caplog.records)


def test_at_most_one_reply_per_request():
    opted_in_doctor()
    DoctorFactory(phone_number="01155555555")
    post(
        text_message("stop"),
        text_message("hello", sender="201155555555"),
        text_message("stop"),
    )
    assert len(sent()) == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reply_is_sent_after_commit(monkeypatch):
    doctor = opted_in_doctor()
    seen = {}
    client = providers.get_whatsapp_client()

    def spy(*, to, body):
        seen["in_atomic"] = connection.in_atomic_block
        seen["opt_in"] = Doctor.objects.get(pk=doctor.pk).whatsapp_opt_in
        return "id"

    monkeypatch.setattr(client, "send_text", spy)
    post(text_message("stop"))
    assert seen == {"in_atomic": False, "opt_in": False}


def test_message_text_is_never_logged_or_stored(caplog):
    opted_in_doctor()
    secret_text = "كلمة-سرية-12345 +201012345678"
    with caplog.at_level(logging.DEBUG):
        post(text_message(secret_text))
        post(text_message("stop"))
    assert "سرية" not in caplog.text
    assert SENDER not in caplog.text
    assert PHONE not in caplog.text
    for entry in AuditLog.objects.all():
        assert "سرية" not in json.dumps(entry.metadata, ensure_ascii=False)


@pytest.mark.parametrize(
    "message",
    [None, 5, "x", [], {}, {"from": 5}, {"from": SENDER}, {"from": SENDER, "type": "text"},
     {"from": SENDER, "type": "text", "text": "stop"},
     {"from": SENDER, "type": "text", "text": {"body": 5}}],
)  # fmt: skip
def test_malformed_messages_never_raise(message):
    opted_in_doctor()
    assert post(message).status_code == 200


def test_malformed_message_does_not_block_the_next_one():
    doctor = opted_in_doctor()
    post({"from": 5}, text_message("stop"))
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False


def test_reply_hides_the_number_in_its_repr():
    opted_in_doctor()
    reply = handle_message(text_message("stop"), now=timezone.now())
    assert isinstance(reply, Reply)
    assert reply.to == "+201012345678"
    assert "201012345678" not in repr(reply)
