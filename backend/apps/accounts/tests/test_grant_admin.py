import pytest
from django.core.management import CommandError, call_command

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def test_grant_admin_by_email_is_case_insensitive():
    user = UserFactory(email="doc@example.test")
    call_command("grant_admin", "DOC@Example.test")
    user.refresh_from_db()
    assert user.role == Role.ADMIN
    entry = AuditLog.objects.get(action=AuditAction.ADMIN_ROLE_GRANTED)
    assert entry.object_id == user.pk
    assert entry.user is None  # system action


def test_grant_admin_by_entra_object_id():
    user = UserFactory(entra_oid="11111111-2222-3333-4444-555555555555", entra_tid="t")
    call_command("grant_admin", "11111111-2222-3333-4444-555555555555")
    user.refresh_from_db()
    assert user.role == Role.ADMIN


def test_grant_admin_unknown_user_fails():
    with pytest.raises(CommandError):
        call_command("grant_admin", "nobody@example.test")


def test_grant_admin_is_idempotent():
    UserFactory(email="doc@example.test")
    call_command("grant_admin", "doc@example.test")
    call_command("grant_admin", "doc@example.test")
    assert AuditLog.objects.filter(action=AuditAction.ADMIN_ROLE_GRANTED).count() == 1
