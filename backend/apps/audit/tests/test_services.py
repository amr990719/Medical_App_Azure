import pytest
from django.test import RequestFactory

from apps.accounts.factories import UserFactory
from apps.applications.factories import ApplicationFactory
from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import record

pytestmark = pytest.mark.django_db


def test_record_creates_an_entry_for_the_object():
    app = ApplicationFactory()
    user = app.doctor.user
    entry = record(actor=user, action=AuditAction.APPLICATION_CREATED, obj=app)
    assert entry.user == user
    assert entry.object_type == "InsuranceApplication"
    assert entry.object_id == app.pk
    assert AuditLog.objects.count() == 1


def test_record_strips_sensitive_metadata_keys():
    entry = record(
        actor=UserFactory(),
        action=AuditAction.APPLICATION_CREATED,
        obj=ApplicationFactory(),
        metadata={"national_id": "29501230101234", "fields": ["national_id"], "token": "abc"},
    )
    assert entry.metadata == {"fields": ["national_id"]}


def test_record_hashes_the_ip_address():
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.7")
    entry = record(
        actor=UserFactory(),
        action=AuditAction.APPLICATION_CREATED,
        obj=ApplicationFactory(),
        request=request,
    )
    assert entry.ip_hash
    assert "203.0.113.7" not in entry.ip_hash
    assert len(entry.ip_hash) == 64


def test_record_without_actor_is_a_system_action():
    entry = record(actor=None, action=AuditAction.FEE_SCHEDULE_CHANGED, obj=ApplicationFactory())
    assert entry.user is None
