"""`still_relevant` re-reads the source of the news at claim time."""

import pytest
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.applications.models import InsuranceApplication
from apps.dues.models import SyndicateDuesRequest
from apps.notifications.factories import NotificationFactory
from apps.notifications.services import still_relevant
from apps.reference.constants import NotificationEvent as E

pytestmark = pytest.mark.django_db

DUES_EVENTS = {E.DUES_REQUESTED, E.DUES_CONFIRMED, E.DUES_RECEIPT_REJECTED, E.DUES_CANCELLED}


def make_row(event, source_state):
    app = ApplicationFactory()
    dues = None
    app_fields = {k: v for k, v in source_state.items() if k in ("status", "payment_status")}
    if app_fields.get("status", "DRAFT") != "DRAFT":
        app_fields.update(reference_number="MED-2026-000001", submitted_at=timezone.now())
    if app_fields:
        InsuranceApplication.objects.filter(pk=app.pk).update(**app_fields)
    if event in DUES_EVENTS:
        admin = AdminUserFactory()
        status = source_state["dues_status"]
        final = status in ("CONFIRMED", "CANCELLED")
        dues = SyndicateDuesRequest.objects.create(
            application=app,
            amount=100,
            reason="x",
            status=status,
            created_by=admin,
            cancellation_reason="x" if status == "CANCELLED" else "",
            resolved_by=admin if final else None,
            resolved_at=timezone.now() if final else None,
        )
    return NotificationFactory(application=app, dues_request=dues, event=event)


@pytest.mark.parametrize(
    "event,source_state,expected",
    [
        ("CORRECTION_NEEDED", {"status": "NEEDS_CORRECTION"}, True),
        ("CORRECTION_NEEDED", {"status": "SUBMITTED"}, False),
        ("PAYMENT_CONFIRMED", {"payment_status": "CONFIRMED"}, True),
        ("PAYMENT_CONFIRMED", {"payment_status": "REJECTED"}, False),
        ("PAYMENT_RECEIPT_REJECTED", {"payment_status": "REJECTED"}, True),
        ("PAYMENT_RECEIPT_REJECTED", {"payment_status": "PENDING_REVIEW"}, False),
        ("DUES_REQUESTED", {"dues_status": "REQUESTED"}, True),
        ("DUES_REQUESTED", {"dues_status": "PENDING_REVIEW"}, False),
        ("DUES_REQUESTED", {"dues_status": "CANCELLED"}, False),
        ("DUES_RECEIPT_REJECTED", {"dues_status": "REJECTED"}, True),
        ("DUES_RECEIPT_REJECTED", {"dues_status": "PENDING_REVIEW"}, False),
    ],
)
def test_still_relevant(event, source_state, expected):
    assert still_relevant(make_row(event, source_state)) is expected


def test_relevance_reads_the_database_not_a_stale_row():
    row = make_row("PAYMENT_CONFIRMED", {"payment_status": "CONFIRMED"})
    InsuranceApplication.objects.filter(pk=row.application_id).update(payment_status="REJECTED")
    assert still_relevant(row) is False


@pytest.mark.parametrize(
    "event", ["APPLICATION_RECEIVED", "APPROVED", "REJECTED", "DUES_CONFIRMED", "DUES_CANCELLED"]
)
def test_other_events_are_always_relevant(event):
    state = {"dues_status": "CONFIRMED"} if event in DUES_EVENTS else {}
    assert still_relevant(make_row(event, state)) is True
