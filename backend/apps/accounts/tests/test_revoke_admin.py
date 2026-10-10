from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def test_revoke_admin_by_email_is_case_insensitive():
    AdminUserFactory()  # another admin remains
    admin = AdminUserFactory(email="boss@example.test")
    call_command("revoke_admin", "BOSS@Example.test", stdout=StringIO())
    admin.refresh_from_db()
    assert admin.role == Role.DOCTOR
    entry = AuditLog.objects.get(action=AuditAction.ADMIN_ROLE_REVOKED)
    assert entry.object_id == admin.pk
    assert entry.user is None  # system action


def test_revoke_admin_by_entra_object_id():
    AdminUserFactory()
    admin = AdminUserFactory(entra_oid="11111111-2222-3333-4444-555555555555", entra_tid="t")
    call_command("revoke_admin", "11111111-2222-3333-4444-555555555555", stdout=StringIO())
    admin.refresh_from_db()
    assert admin.role == Role.DOCTOR


def test_revoke_admin_unknown_user_fails():
    with pytest.raises(CommandError):
        call_command("revoke_admin", "nobody@example.test")


def test_revoke_admin_on_a_doctor_changes_nothing():
    UserFactory(email="doc@example.test")
    out = StringIO()
    call_command("revoke_admin", "doc@example.test", stdout=out)
    assert "nothing changed" in out.getvalue()
    assert not AuditLog.objects.filter(action=AuditAction.ADMIN_ROLE_REVOKED).exists()


def test_revoke_admin_refuses_to_remove_the_last_admin():
    admin = AdminUserFactory(email="only@example.test")
    with pytest.raises(CommandError, match="last administrator"):
        call_command("revoke_admin", "only@example.test")
    admin.refresh_from_db()
    assert admin.role == Role.ADMIN
    assert not AuditLog.objects.filter(action=AuditAction.ADMIN_ROLE_REVOKED).exists()


def test_revoke_admin_ends_the_users_existing_sessions():
    AdminUserFactory()
    admin = AdminUserFactory(email="leaving@example.test")
    client = Client()
    client.force_login(admin, backend="apps.accounts.backends.SessionOnlyBackend")
    assert client.get("/api/v1/admin/stats/").status_code == 200
    call_command("revoke_admin", "leaving@example.test", stdout=StringIO())
    assert client.get("/api/v1/admin/stats/").status_code in {401, 403}
