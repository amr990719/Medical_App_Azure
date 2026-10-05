import pytest
from django.test import override_settings

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import ApplicationFactory
from apps.audit.models import AuditAction, AuditLog
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.beneficiaries.services import (
    beneficiary_warnings,
    check_kinship_rules,
    delete_beneficiary,
    upsert_beneficiary,
)
from apps.common.exceptions import ApplicationNotEditable, PermissionDeniedError, ValidationFailed
from apps.documents.factories import DocumentFactory
from apps.documents.models import Document
from apps.reference.constants import ApplicationStatus, Gender, Kinship
from apps.reference.constants import DocumentType as D

pytestmark = pytest.mark.django_db


def upsert(app, actor=None, **fields):
    data = {
        "row_number": 1, "kinship": Kinship.SON_MINOR, "full_name": "عمر أحمد",
        "birth_year": 2015, "national_id": None, **fields,
    }  # fmt: skip
    return upsert_beneficiary(app, actor=actor or app.doctor.user, **data)


# --- upsert -----------------------------------------------------------------------------------


def test_creates_then_updates_the_same_row():
    app = ApplicationFactory()
    b = upsert(app)
    b2 = upsert(app, full_name="عمر أحمد محمد")
    assert b2.pk == b.pk
    assert app.beneficiaries.get().full_name == "عمر أحمد محمد"


def test_normalizes_arabic_digits_names_and_blank_ids():
    app = ApplicationFactory()
    b = upsert(app, national_id="٢٩٠٠١٠١٠١٠١٢٣٤", full_name="  عمر   أحمد ")
    assert b.national_id == "29001010101234"
    assert b.full_name == "عمر أحمد"
    assert upsert(app, row_number=2, national_id="  ").national_id is None


def test_malformed_national_id_rejected():
    app = ApplicationFactory()
    with pytest.raises(ValidationFailed) as exc:
        upsert(app, national_id="12345")
    assert exc.value.fields == {"national_id": ["الرقم القومي يجب أن يكون 14 رقماً صحيحاً"]}


def test_national_id_equal_to_member_rejected():
    app = ApplicationFactory()
    with pytest.raises(ValidationFailed) as exc:
        upsert(app, national_id=app.doctor.national_id)
    assert "national_id" in exc.value.fields


def test_duplicate_national_id_in_same_application_rejected():
    app = ApplicationFactory()
    upsert(app, row_number=1, national_id="29001010101234")
    with pytest.raises(ValidationFailed) as exc:
        upsert(app, row_number=2, national_id="29001010101234")
    assert "national_id" in exc.value.fields


def test_eleventh_row_rejected():
    app = ApplicationFactory()
    with pytest.raises(ValidationFailed) as exc:
        upsert(app, row_number=11)
    assert "row_number" in exc.value.fields


@override_settings(MAX_BENEFICIARIES=11)
def test_max_beneficiaries_is_configurable():
    assert upsert(ApplicationFactory(), row_number=11).row_number == 11


@pytest.mark.parametrize("birth_year", [99999, 12, -1])
def test_out_of_range_birth_year_rejected_at_draft_level(birth_year):
    with pytest.raises(ValidationFailed) as exc:
        upsert(ApplicationFactory(), birth_year=birth_year)
    assert "birth_year" in exc.value.fields


def test_unknown_kinship_rejected():
    with pytest.raises(ValidationFailed) as exc:
        upsert(ApplicationFactory(), kinship="BROTHER")
    assert "kinship" in exc.value.fields


@pytest.mark.parametrize("status", [ApplicationStatus.SUBMITTED, ApplicationStatus.APPROVED])
def test_not_editable_raises(status):
    app = ApplicationFactory(status=status, reference_number="MED-2026-000001")
    with pytest.raises(ApplicationNotEditable):
        upsert(app)


def test_needs_correction_is_editable():
    app = ApplicationFactory(
        status=ApplicationStatus.NEEDS_CORRECTION, reference_number="MED-2026-000001"
    )
    assert upsert(app).pk


def test_other_doctor_cannot_edit():
    with pytest.raises(PermissionDeniedError):
        upsert(ApplicationFactory(), actor=UserFactory())


def test_admin_cannot_edit_a_doctors_draft():
    with pytest.raises(PermissionDeniedError):
        upsert(ApplicationFactory(), actor=AdminUserFactory())


# --- kinship change removes documents ---------------------------------------------------------


def test_kinship_change_soft_deletes_documents():
    app = ApplicationFactory()
    b = upsert(app)
    doc = DocumentFactory(application=app, beneficiary=b, document_type=D.BIRTH_CERTIFICATE)
    upsert(app, kinship=Kinship.DAUGHTER)
    doc.refresh_from_db()
    assert doc.deleted_at is not None
    assert not Document.objects.filter(beneficiary=b).exists()
    entry = AuditLog.objects.get(action=AuditAction.DOCUMENT_DELETED)
    assert entry.object_id == doc.pk
    assert entry.metadata["reason"] == "KINSHIP_CHANGED"


def test_same_kinship_keeps_documents():
    app = ApplicationFactory()
    b = upsert(app)
    doc = DocumentFactory(application=app, beneficiary=b, document_type=D.BIRTH_CERTIFICATE)
    upsert(app, full_name="عمر أحمد محمد")
    doc.refresh_from_db()
    assert doc.deleted_at is None


def test_delete_beneficiary_soft_deletes_its_documents():
    app = ApplicationFactory()
    b = upsert(app)
    doc = DocumentFactory(application=app, beneficiary=b, document_type=D.BIRTH_CERTIFICATE)
    delete_beneficiary(b, actor=app.doctor.user)
    assert not app.beneficiaries.exists()
    doc = Document.all_objects.get(pk=doc.pk)
    assert doc.deleted_at is not None
    assert doc.beneficiary is None
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_DELETED).count() == 1


def test_delete_beneficiary_requires_editable_application():
    b = BeneficiaryFactory(
        application=ApplicationFactory(
            status=ApplicationStatus.SUBMITTED, reference_number="MED-2026-000001"
        )
    )
    with pytest.raises(ApplicationNotEditable):
        delete_beneficiary(b, actor=b.application.doctor.user)


# --- kinship rules (configurable) -------------------------------------------------------------


def rule_fields(kinship, birth_year, member_gender):
    return [e.field for e in check_kinship_rules(
        kinship=kinship, birth_year=birth_year, row_number=3, name="س",
        member_gender=member_gender, fiscal_year=2026,
    )]  # fmt: skip


def test_wife_requires_male_member_when_enforced():
    assert rule_fields(Kinship.WIFE, 1990, Gender.FEMALE) == ["beneficiaries[3].kinship"]
    assert rule_fields(Kinship.WIFE, 1990, Gender.MALE) == []


def test_husband_requires_female_member():
    assert rule_fields(Kinship.HUSBAND, 1990, Gender.MALE) == ["beneficiaries[3].kinship"]
    assert rule_fields(Kinship.HUSBAND, 1990, Gender.FEMALE) == []


@override_settings(ENFORCE_SPOUSE_GENDER=False)
def test_spouse_gender_rule_can_be_disabled():
    assert rule_fields(Kinship.WIFE, 1990, Gender.FEMALE) == []


def test_son_minor_over_18_flagged():
    assert rule_fields(Kinship.SON_MINOR, 2007, Gender.MALE) == ["beneficiaries[3].kinship"]
    assert rule_fields(Kinship.SON_MINOR, 2008, Gender.MALE) == []  # exactly 18
    assert rule_fields(Kinship.SON_MINOR, None, Gender.MALE) == []


@override_settings(ENFORCE_SON_MINOR_AGE=False)
def test_son_minor_rule_can_be_disabled():
    assert rule_fields(Kinship.SON_MINOR, 2000, Gender.MALE) == []


def test_kinship_rule_messages_are_arabic_and_name_the_beneficiary():
    errors = check_kinship_rules(
        kinship=Kinship.WIFE, birth_year=1990, row_number=1, name="سارة",
        member_gender=Gender.FEMALE, fiscal_year=2026,
    )  # fmt: skip
    assert errors[0].message.startswith("المستفيد سارة:")
    assert errors[0].step == 2


# --- warnings ---------------------------------------------------------------------------------


def test_cross_application_duplicate_is_warning():
    first = BeneficiaryFactory(national_id="31501010101234", full_name="عمر")
    second = BeneficiaryFactory(national_id="31501010101234", full_name="عمر")
    assert len(beneficiary_warnings(second)) == 1
    assert len(beneficiary_warnings(first)) == 1


def test_no_warning_without_duplicates():
    assert beneficiary_warnings(BeneficiaryFactory(national_id="31501010101234")) == []
    assert beneficiary_warnings(BeneficiaryFactory(national_id=None)) == []


def test_warning_ignores_rejected_applications():
    BeneficiaryFactory(
        national_id="31501010101234",
        application=ApplicationFactory(
            status=ApplicationStatus.REJECTED, reference_number="MED-2026-000009"
        ),
    )
    assert beneficiary_warnings(BeneficiaryFactory(national_id="31501010101234")) == []
