from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.factories import AdminUserFactory, UserFactory
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


def test_granting_admin_ends_the_users_existing_sessions():
    # MFA is checked when an admin signs in (ENTRA_ADMIN_REQUIRE_MFA). A doctor session opened
    # without MFA must not turn into an admin session: the role change signs the user out.
    from django.test import Client

    user = UserFactory(email="promoted@example.test")
    client = Client()
    client.force_login(user, backend="apps.accounts.backends.SessionOnlyBackend")
    assert client.get("/api/v1/auth/me/").status_code == 200
    call_command("grant_admin", "promoted@example.test", stdout=StringIO())
    assert client.get("/api/v1/auth/me/").status_code == 401
    assert client.get("/api/v1/admin/stats/").status_code in {401, 403}


def test_revoking_admin_ends_the_users_existing_sessions():
    from django.test import Client

    admin = AdminUserFactory()
    client = Client()
    client.force_login(admin, backend="apps.accounts.backends.SessionOnlyBackend")
    assert client.get("/api/v1/admin/stats/").status_code == 200
    admin.role = Role.DOCTOR
    admin.save(update_fields=["role"])
    assert client.get("/api/v1/auth/me/").status_code == 401
