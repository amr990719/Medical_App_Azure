import pytest
from django.db import IntegrityError

from apps.accounts.models import Role, User


@pytest.mark.django_db
class TestUser:
    def test_primary_key_is_uuid(self):
        user = User.objects.create_user(email="doc@example.test")
        assert len(str(user.pk)) == 36

    def test_email_is_normalized_to_lowercase(self):
        user = User.objects.create_user(email="  Doc@Example.TEST ")
        assert user.email == "doc@example.test"

    def test_email_is_case_insensitive_unique(self):
        User.objects.create_user(email="doc@example.test")
        with pytest.raises(IntegrityError):
            User.objects.create_user(email="DOC@example.test")

    def test_database_enforces_case_insensitive_email(self):
        User.objects.create_user(email="doc@example.test")
        # Bypass the manager's normalization: the functional unique index must still refuse.
        with pytest.raises(IntegrityError):
            User.objects.bulk_create([User(email="Doc@Example.test")])

    def test_new_user_is_doctor_without_usable_password(self):
        user = User.objects.create_user(email="doc@example.test")
        assert user.role == Role.DOCTOR
        assert user.is_admin is False
        assert user.has_usable_password() is False

    def test_create_admin_sets_role(self):
        admin = User.objects.create_admin(email="admin@example.test")
        assert admin.role == Role.ADMIN
        assert admin.is_admin is True

    def test_entra_identity_is_unique_per_tenant(self):
        User.objects.create_user(email="a@example.test", entra_oid="oid-1", entra_tid="tid-1")
        with pytest.raises(IntegrityError):
            User.objects.create_user(email="b@example.test", entra_oid="oid-1", entra_tid="tid-1")

    def test_dev_users_may_share_null_entra_identity(self):
        User.objects.create_user(email="a@example.test")
        User.objects.create_user(email="b@example.test")
        assert User.objects.count() == 2
