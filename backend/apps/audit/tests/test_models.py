import uuid

import pytest
from django.db import DatabaseError, transaction

from apps.accounts.factories import UserFactory
from apps.audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def make_entry():
    return AuditLog.objects.create(
        user=UserFactory(),
        action=AuditAction.APPLICATION_CREATED,
        object_type="InsuranceApplication",
        object_id=uuid.uuid4(),
    )


def test_audit_log_is_append_only_through_the_orm():
    entry = make_entry()
    entry.metadata = {"tampered": True}
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()


def test_database_refuses_update():
    entry = make_entry()
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(metadata={"tampered": True})


def test_database_refuses_delete():
    entry = make_entry()
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()


def test_action_catalogue_covers_prompt_section_39():
    required = {
        "APPLICATION_CREATED", "APPLICATION_SUBMITTED", "APPLICATION_RESUBMITTED",
        "APPLICATION_STATUS_CHANGED", "PAYMENT_STATUS_CHANGED", "FEE_SNAPSHOT_CREATED",
        "DOCUMENT_UPLOADED", "DOCUMENT_REPLACED", "DOCUMENT_DELETED", "DOCUMENT_VIEWED",
        "OCR_REQUESTED", "ADMIN_APPLICATION_VIEWED", "ADMIN_NOTE_ADDED", "FEE_SCHEDULE_CHANGED",
        "ADMIN_ROLE_GRANTED",
    }  # fmt: skip
    assert required <= set(AuditAction.values)
