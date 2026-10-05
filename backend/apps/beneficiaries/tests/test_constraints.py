import pytest
from django.db import IntegrityError

from apps.applications.factories import ApplicationFactory
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.beneficiaries.models import Beneficiary
from apps.reference.constants import Kinship

pytestmark = pytest.mark.django_db


def test_beneficiary_duplicate_national_id_in_application_fails():
    b = BeneficiaryFactory(national_id="29001010101234")
    with pytest.raises(IntegrityError):
        BeneficiaryFactory(application=b.application, national_id="29001010101234")


def test_same_national_id_in_another_application_is_allowed():
    BeneficiaryFactory(national_id="29001010101234")
    BeneficiaryFactory(national_id="29001010101234")


def test_two_null_national_ids_allowed():
    app = ApplicationFactory()
    BeneficiaryFactory(application=app, national_id=None)
    BeneficiaryFactory(application=app, national_id=None)
    assert app.beneficiaries.count() == 2


def test_row_number_unique_per_application():
    b = BeneficiaryFactory(row_number=1)
    with pytest.raises(IntegrityError):
        BeneficiaryFactory(application=b.application, row_number=1)


@pytest.mark.parametrize("row_number", [0, 21])
def test_row_number_range_checked_by_database(row_number):
    with pytest.raises(IntegrityError):
        BeneficiaryFactory(row_number=row_number)


def test_malformed_national_id_rejected_by_database():
    with pytest.raises(IntegrityError):
        BeneficiaryFactory(national_id="123")


def test_unknown_kinship_rejected_by_database():
    with pytest.raises(IntegrityError):
        BeneficiaryFactory(kinship="BROTHER")


@pytest.mark.parametrize(
    ("kinship", "name", "active"),
    [(Kinship.WIFE, "سارة", True), (Kinship.WIFE, "  ", False), ("", "سارة", False)],
)
def test_is_active_needs_kinship_and_name(kinship, name, active):
    assert Beneficiary(kinship=kinship, full_name=name).is_active is active
