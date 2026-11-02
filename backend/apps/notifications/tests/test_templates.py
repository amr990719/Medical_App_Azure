from decimal import Decimal

import pytest

from apps.notifications.formatting import (
    format_amount,
    from_whatsapp_sender,
    mask_email,
    mask_phone,
    to_e164,
)
from apps.notifications.models import DUES_EVENTS
from apps.notifications.templates import (
    CLOSING,
    HELP_REPLY,
    MESSAGES,
    STOP_CONFIRMATION,
    WHATSAPP_FOOTER,
    render_email,
    template_parameters,
)
from apps.reference.constants import NotificationEvent


@pytest.mark.parametrize(
    "value,expected",
    [
        ("3025.00", "3٬025 ج.م"),
        ("1250.50", "1٬250.50 ج.م"),
        ("250.00", "250 ج.م"),
        ("99999999.99", "99٬999٬999.99 ج.م"),
        ("3025", "3٬025 ج.م"),
        ("1250.5", "1٬250.50 ج.م"),
        ("0.00", "0 ج.م"),
    ],
)
def test_format_amount(value, expected):
    assert format_amount(Decimal(value)) == expected


def test_masks():
    assert mask_phone("01012345678") == "010•••••678"
    assert mask_email("ahmed@example.com") == "a•••@example.com"


def test_mask_email_never_exceeds_the_column_and_hides_the_address():
    local, domain = "l" * 64, "d" * 63 + "." + "e" * 63 + "." + "f" * 57 + ".com"
    address = f"{local}@{domain}"
    assert len(address) == 254
    masked = mask_email(address)
    assert len(masked) <= 64 and masked.startswith("l•••@")
    assert local not in masked and domain not in masked


def test_to_e164():
    assert to_e164("01012345678") == "+201012345678"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("201012345678", "01012345678"),
        ("+201012345678", "01012345678"),
        ("14155552671", None),
        ("", None),
    ],
)
def test_from_whatsapp_sender(raw, expected):
    assert from_whatsapp_sender(raw) == expected


def test_every_event_has_a_message():
    assert set(MESSAGES) == set(NotificationEvent.values)


@pytest.mark.parametrize("event", sorted(DUES_EVENTS))
def test_dues_messages_carry_the_amount(event):
    assert "{{2}}" in MESSAGES[event].body
    assert template_parameters(event, reference="MED-2026-000123", amount=Decimal("3025")) == [
        "MED-2026-000123",
        "3٬025 ج.م",
    ]


@pytest.mark.parametrize("event", sorted(set(NotificationEvent.values) - DUES_EVENTS))
def test_non_dues_messages_only_carry_the_reference(event):
    assert "{{2}}" not in MESSAGES[event].body
    assert template_parameters(event, reference="MED-2026-000123") == ["MED-2026-000123"]


def test_no_message_claims_nothing_is_owed():
    assert all("لا حاجة" not in m.body for m in MESSAGES.values())


def test_footer_replaces_the_no_replies_line():
    assert WHATSAPP_FOOTER == "لإيقاف الرسائل أرسل: إيقاف"
    assert len(WHATSAPP_FOOTER) <= 60  # Meta's footer limit, NOT VERIFIED for this API version


def test_reply_strings_and_closing():
    assert CLOSING == "يرجى تسجيل الدخول إلى حسابك لمعرفة التفاصيل."
    assert STOP_CONFIRMATION.startswith("تم إيقاف رسائل واتساب")
    assert HELP_REPLY.startswith("لإيقاف الرسائل أرسل: إيقاف.")


def test_email_subject_and_escaping():
    email = render_email(NotificationEvent.APPROVED, reference="MED-2026-000123")
    assert email.subject == "طلبك رقم MED-2026-000123: تم قبول طلبك"
    assert 'dir="rtl"' in email.html and CLOSING in email.text


def test_email_escapes_substituted_values():
    email = render_email(NotificationEvent.APPROVED, reference="<b>x</b>")
    assert "<b>x</b>" not in email.html
    assert "&lt;b&gt;x&lt;/b&gt;" in email.html


def test_email_dues_body_has_amount():
    email = render_email(
        NotificationEvent.DUES_REQUESTED, reference="MED-2026-000123", amount=Decimal("3025")
    )
    assert "3٬025 ج.م" in email.text and "MED-2026-000123" in email.text
