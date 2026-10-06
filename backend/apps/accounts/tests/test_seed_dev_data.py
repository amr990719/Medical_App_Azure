import re
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.accounts.models import Role, User
from apps.applications.models import InsuranceApplication
from apps.doctors.models import Doctor
from apps.documents.models import Document
from apps.fees.models import FeeSchedule
from apps.reference.constants import ApplicationStatus, PaymentStatus

pytestmark = pytest.mark.django_db

REFERENCE = re.compile(r"MED-2026-\d{6}")


def seed() -> str:
    out = StringIO()
    call_command("seed_dev_data", stdout=out)
    return out.getvalue()


def application_of(email: str) -> InsuranceApplication:
    return InsuranceApplication.objects.get(doctor__user__email=email, fiscal_year=2026)


def test_seed_creates_doctors_and_an_admin_for_the_dev_login():
    seed()
    assert User.objects.filter(role=Role.ADMIN, email="admin@dev.local").exists()
    doctors = Doctor.objects.filter(user__email__endswith="@dev.local")
    assert doctors.count() == 3
    complete = Doctor.objects.get(user__email="doctor@dev.local")
    assert complete.national_id and complete.syndicate_registration_year == 2014
    empty = Doctor.objects.get(user__email="new.doctor@dev.local")
    assert empty.national_id is None and empty.full_name == ""
    assert not InsuranceApplication.objects.filter(doctor=empty).exists()
    assert not any(u.has_usable_password() for u in User.objects.all())


def test_seed_submits_the_worked_example_2_application_waiting_for_payment_review():
    seed()
    app = application_of("doctor@dev.local")
    assert app.status == ApplicationStatus.SUBMITTED
    assert app.payment_status == PaymentStatus.PENDING_REVIEW
    assert REFERENCE.fullmatch(app.reference_number)
    assert (app.fee_snapshot["tier"], app.fee_snapshot["total"]) == (3, 3025)
    kinships = sorted(app.beneficiaries.values_list("kinship", flat=True))
    assert kinships == ["DAUGHTER", "SON_MINOR", "WIFE"]
    types = set(Document.objects.filter(application=app).values_list("document_type", flat=True))
    assert {"NATIONAL_ID_FRONT", "PAYMENT_RECEIPT", "MARRIAGE_CERTIFICATE"} <= types


def test_seed_gives_the_second_doctor_an_application_needing_correction():
    seed()
    app = application_of("doctor2@dev.local")
    assert app.status == ApplicationStatus.NEEDS_CORRECTION
    assert app.review_notes
    assert REFERENCE.fullmatch(app.reference_number)
    assert app.reviewed_by.email == "admin@dev.local"
    assert app.doctor.gender == "FEMALE"
    assert app.fee_snapshot["total"] == 2075  # tier 2: 700 + mother 1200 + 175


def test_seed_ensures_the_fy2026_fee_schedule():
    FeeSchedule.objects.all().delete()
    seed()
    schedule = FeeSchedule.objects.get(fiscal_year=2026, is_active=True)
    assert schedule.tier_fees["3"] == {
        "member": 750, "spouse": 1000, "child": 550, "grad_son": 1500, "parent": 1300,
    }  # fmt: skip
    assert (schedule.admin_fee_member_only, schedule.admin_fee_with_beneficiaries) == (150, 175)


def test_seed_is_idempotent():
    seed()
    first = {a.pk: a.reference_number for a in InsuranceApplication.objects.all()}
    seed()
    assert User.objects.filter(email__endswith="@dev.local").count() == 4
    assert {a.pk: a.reference_number for a in InsuranceApplication.objects.all()} == first
    assert FeeSchedule.objects.filter(fiscal_year=2026).count() == 1


@override_settings(DEV_AUTH_ENABLED=False)
def test_seed_refuses_without_dev_auth():
    with pytest.raises(CommandError):
        seed()
