import pytest
from django.db import IntegrityError, transaction

from apps.applications.factories import ApplicationFactory
from apps.applications.models import InsuranceApplication, ReferenceCounter
from apps.doctors.models import Doctor
from apps.reference.constants import ApplicationStatus as S

pytestmark = pytest.mark.django_db


def test_new_application_defaults():
    app = ApplicationFactory()
    assert app.status == S.DRAFT
    assert app.payment_status == "NOT_UPLOADED"
    assert app.reference_number is None
    assert app.is_editable is True


def test_second_active_application_same_year_violates_constraint():
    app = ApplicationFactory()
    with pytest.raises(IntegrityError):
        ApplicationFactory(doctor=app.doctor, fiscal_year=app.fiscal_year)


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.NEEDS_CORRECTION, S.APPROVED])
def test_any_non_rejected_status_blocks_a_second_application(status):
    app = ApplicationFactory(status=status, reference_number="MED-2026-000001")
    with pytest.raises(IntegrityError):
        ApplicationFactory(doctor=app.doctor)


def test_rejected_application_allows_new_one():
    app = ApplicationFactory(status=S.REJECTED, reference_number="MED-2026-000001")
    ApplicationFactory(doctor=app.doctor)
    assert InsuranceApplication.objects.filter(doctor=app.doctor).count() == 2


def test_same_doctor_different_fiscal_years_allowed():
    app = ApplicationFactory(fiscal_year=2026)
    ApplicationFactory(doctor=app.doctor, fiscal_year=2027)


def test_reference_number_is_unique():
    ApplicationFactory(status=S.SUBMITTED, reference_number="MED-2026-000001")
    with pytest.raises(IntegrityError):
        ApplicationFactory(status=S.SUBMITTED, reference_number="MED-2026-000001")


def test_draft_cannot_carry_a_reference_number():
    with pytest.raises(IntegrityError):
        ApplicationFactory(status=S.DRAFT, reference_number="MED-2026-000001")


def test_submitted_application_must_carry_a_reference_number():
    with pytest.raises(IntegrityError):
        ApplicationFactory(status=S.SUBMITTED, reference_number=None)


def test_reference_number_format_is_enforced():
    with pytest.raises(IntegrityError):
        ApplicationFactory(status=S.SUBMITTED, reference_number="2026-1")


def test_unknown_status_rejected_by_database():
    app = ApplicationFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        InsuranceApplication.objects.filter(pk=app.pk).update(status="HACKED")


@pytest.mark.parametrize(
    ("status", "editable"),
    [
        (S.DRAFT, True),
        (S.NEEDS_CORRECTION, True),
        (S.SUBMITTED, False),
        (S.UNDER_REVIEW, False),
        (S.APPROVED, False),
        (S.REJECTED, False),
    ],
)
def test_is_editable(status, editable):
    assert InsuranceApplication(status=status).is_editable is editable


def test_doctor_with_applications_cannot_be_deleted():
    from django.db.models import ProtectedError

    app = ApplicationFactory()
    with pytest.raises(ProtectedError):
        Doctor.objects.filter(pk=app.doctor.pk).delete()


def test_admin_filter_indexes_exist():
    names = {i.name for i in InsuranceApplication._meta.indexes}
    assert {"app_status_submitted_idx", "app_year_status_idx", "app_payment_status_idx"} <= names


def test_reference_counter_unique_per_year():
    ReferenceCounter.objects.create(fiscal_year=2026)
    with pytest.raises(IntegrityError):
        ReferenceCounter.objects.create(fiscal_year=2026)
