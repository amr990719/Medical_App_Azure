from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.accounts.models import Role, User
from apps.doctors.models import Doctor

pytestmark = pytest.mark.django_db


def seed() -> str:
    out = StringIO()
    call_command("seed_dev_data", stdout=out)
    return out.getvalue()


def test_seed_creates_doctors_and_an_admin_for_the_dev_login():
    seed()
    assert User.objects.filter(role=Role.ADMIN, email="admin@dev.local").exists()
    doctors = Doctor.objects.filter(user__email__endswith="@dev.local")
    assert doctors.count() == 2
    complete = Doctor.objects.get(user__email="doctor@dev.local")
    assert complete.national_id and complete.syndicate_registration_year == 2014
    empty = Doctor.objects.get(user__email="new.doctor@dev.local")
    assert empty.national_id is None and empty.full_name == ""
    assert not any(u.has_usable_password() for u in User.objects.all())


def test_seed_is_idempotent():
    seed()
    seed()
    assert User.objects.filter(email__endswith="@dev.local").count() == 3


@override_settings(DEV_AUTH_ENABLED=False)
def test_seed_refuses_without_dev_auth():
    with pytest.raises(CommandError):
        seed()
