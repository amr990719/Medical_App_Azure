"""Submission validation — every rule of PROMPT.md §22 with its exact Arabic message."""

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.applications.factories import ApplicationFactory, build_submittable_application
from apps.applications.validation import validate_for_submission
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.doctors.factories import DoctorFactory
from apps.documents.models import Document
from apps.reference.constants import DocumentType as D
from apps.reference.constants import Gender, Kinship

pytestmark = pytest.mark.django_db


def errors_of(app, stage="submit"):
    return validate_for_submission(app, stage=stage).errors


def find(app, field, stage="submit"):
    matches = [e for e in errors_of(app, stage) if e.field == field]
    assert matches, f"no error for {field}: {[e.field for e in errors_of(app, stage)]}"
    return matches[0]


def assert_error(app, field, step, message):
    error = find(app, field)
    assert (error.step, error.message) == (step, message)


def remove_document(app, doc_type, beneficiary=None):
    Document.objects.filter(
        application=app, document_type=doc_type, beneficiary=beneficiary
    ).update(deleted_at=timezone.now())


def update_doctor(app, **fields):
    for key, value in fields.items():
        setattr(app.doctor, key, value)
    app.doctor.save()


@pytest.fixture
def app():
    return build_submittable_application()


# --- baseline ---------------------------------------------------------------------------------


def test_complete_application_is_valid(app):
    result = validate_for_submission(app)
    assert result.errors == []
    assert result.is_valid is True
    assert result.steps == {1: True, 2: True, 3: True, 4: True, 5: True}


# --- step 1: member ---------------------------------------------------------------------------


def test_rule_01_syndicate_type_required(app):
    update_doctor(app, syndicate_type="")
    assert_error(app, "member.syndicate_type", 1, "يرجى اختيار نوع النقابة")


def test_rule_02_member_name_at_least_5_characters(app):
    update_doctor(app, full_name=" أحمد ")
    assert_error(app, "member.full_name", 1, "اسم العضو يجب أن يكون 5 أحرف على الأقل")


def test_rule_03_national_id_required_and_valid(app):
    update_doctor(app, national_id=None)
    assert_error(app, "member.national_id", 1, "الرقم القومي يجب أن يكون 14 رقماً صحيحاً")


def test_rule_03_impossible_date_in_national_id(app):
    app.doctor.national_id = "29502300101234"  # 30 February, in memory only
    assert_error(app, "member.national_id", 1, "الرقم القومي يجب أن يكون 14 رقماً صحيحاً")


def test_rule_04_gender_required(app):
    update_doctor(app, gender="")
    assert_error(app, "member.gender", 1, "يرجى تحديد النوع (ذكر/أنثى)")


def test_rule_04_gender_must_match_national_id(app):
    update_doctor(app, gender=Gender.FEMALE)  # the factory ID encodes a male
    error = find(app, "member.gender")
    assert error.message == "يرجى تحديد النوع (ذكر/أنثى)"
    assert error.code == "GENDER_MISMATCH"


def test_birth_year_must_match_national_id(app):
    update_doctor(app, birth_year=1986)
    assert_error(app, "member.birth_year", 1, "سنة الميلاد لا تطابق الرقم القومي")


def test_rule_05_work_status_required(app):
    app.work_status = ""
    app.save()
    assert_error(app, "member.work_status", 1, "يرجى تحديد حالة العمل")


@pytest.mark.parametrize("year", [None, 1949, 2027])
def test_rule_06_registration_year_range(app, year):
    update_doctor(app, syndicate_registration_year=year)
    assert_error(app, "member.syndicate_registration_year", 1, "سنة قيد النقابة غير صحيحة")


@pytest.mark.parametrize("year", [1950, 2026])
def test_rule_06_registration_year_bounds_are_inclusive(app, year):
    update_doctor(app, syndicate_registration_year=year)
    assert validate_for_submission(app).is_valid


@pytest.mark.parametrize("phone", ["", "0123", "01312345678"])
def test_rule_07_mobile(app, phone):
    update_doctor(app, phone_number=phone)
    assert_error(app, "member.phone_number", 1, "رقم الهاتف المحمول غير صحيح")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("governorate", "", "يرجى إدخال محافظة السكن"),
        ("governorate", "باريس", "يرجى إدخال محافظة السكن"),
        ("address", "  ", "يرجى إدخال العنوان"),
        ("sub_syndicate", "", "يرجى إدخال النقابة الفرعية"),
        ("syndicate_registration_number", "", "يرجى إدخال رقم قيد النقابة"),
        ("birth_year", None, "يرجى إدخال سنة الميلاد"),
    ],
)
def test_rule_14_required_member_fields(app, field, value, message):
    update_doctor(app, **{field: value})
    assert_error(app, f"member.{field}", 1, message)


def test_rule_18_national_id_used_by_another_doctor(app):
    other = DoctorFactory()
    app.doctor.national_id = other.national_id  # in memory: the DB constraint forbids saving it
    error = find(app, "member.national_id")
    assert (error.step, error.code, error.message) == (
        1,
        "DUPLICATE_NATIONAL_ID",
        "الرقم القومي مسجل لعضو آخر",
    )


# --- step 3: member documents -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("doc_type", "message"),
    [
        (D.NATIONAL_ID_FRONT, "يرجى إرفاق صورة وجه البطاقة الشخصية"),
        (D.NATIONAL_ID_BACK, "يرجى إرفاق صورة ظهر البطاقة الشخصية"),
        (D.SYNDICATE_ID, "يرجى إرفاق صورة كارنيه النقابة"),
    ],
)
def test_rules_08_to_10_member_documents(app, doc_type, message):
    remove_document(app, doc_type)
    assert_error(app, f"documents.{doc_type}", 3, message)


def test_member_photo_optional_by_default(app):
    assert validate_for_submission(app).is_valid


@override_settings(REQUIRE_MEMBER_PHOTO=True)
def test_member_photo_required_when_configured(app):
    assert_error(app, "documents.PERSONAL_PHOTO", 3, "يرجى إرفاق صورة العضو الأصلي")


# --- step 2: beneficiaries --------------------------------------------------------------------


def test_rule_11_named_beneficiary_needs_kinship(app):
    BeneficiaryFactory(application=app, row_number=4, kinship="", full_name="خالد أحمد")
    assert_error(app, "beneficiaries[4].kinship", 2, "المستفيد رقم 4: يرجى تحديد درجة القرابة")


@pytest.mark.parametrize("birth_year", [None, 1919, 2027])
def test_rule_12_beneficiary_birth_year(app, birth_year):
    app.beneficiaries.filter(row_number=1).update(birth_year=birth_year)
    assert_error(
        app, "beneficiaries[1].birth_year", 2, "المستفيد سارة محمود علي: سنة الميلاد غير صحيحة"
    )


def test_kinship_without_name_is_ignored(app):
    # Worked example 8: such a row is not active — no errors, no fee.
    BeneficiaryFactory(application=app, row_number=4, kinship=Kinship.WIFE, full_name="  ")
    assert validate_for_submission(app).is_valid


def test_section_14_spouse_gender_rule(app):
    app.beneficiaries.filter(row_number=1).update(kinship=Kinship.HUSBAND)
    error = find(app, "beneficiaries[1].kinship")
    assert error.code == "SPOUSE_GENDER_MISMATCH"
    assert error.step == 2


def test_section_14_son_minor_age_rule(app):
    app.beneficiaries.filter(row_number=2).update(birth_year=2006)
    assert find(app, "beneficiaries[2].kinship").code == "SON_MINOR_TOO_OLD"


def test_section_14_beneficiary_id_equal_to_member(app):
    app.doctor.national_id = "28803150101242"  # the wife's ID, in memory
    update_doctor(app, gender=Gender.FEMALE, birth_year=1988)
    assert find(app, "beneficiaries[1].national_id").step == 2


# --- step 3: beneficiary documents (rule 13, driven by document_rules) ------------------------


def test_rule_13_beneficiary_required_document(app):
    wife = app.beneficiaries.get(row_number=1)
    remove_document(app, D.MARRIAGE_CERTIFICATE, beneficiary=wife)
    assert_error(
        app, "beneficiaries[1].documents.MARRIAGE_CERTIFICATE", 3,
        "المستفيد سارة محمود علي: مستند شهادة الزواج مطلوب",
    )  # fmt: skip


def test_rule_13_uses_the_age_aware_child_rule(app):
    # A 16-year-old son of a male member needs his national ID, not the birth certificate.
    son = app.beneficiaries.get(row_number=2)
    son.birth_year = 2010
    son.save()
    error = find(app, "beneficiaries[2].documents.BENEFICIARY_NATIONAL_ID")
    assert error.message == "المستفيد عمر أحمد محمد: مستند بطاقة الرقم القومي مطلوب"


# --- step 4 / 5: receipt and declaration ------------------------------------------------------


def test_rule_15_declaration_name_must_match(app):
    app.declaration_name = "اسم شخص آخر"
    app.save()
    assert_error(app, "declaration.name", 5, "اسم المقر يجب أن يطابق اسم العضو")


def test_rule_15_empty_declaration_name(app):
    app.declaration_name = ""
    app.save()
    assert_error(app, "declaration.name", 5, "اسم المقر يجب أن يطابق اسم العضو")


def test_declaration_name_normalization(app):
    update_doctor(app, full_name="أحمد محمّد علي")
    app.declaration_name = "  احمد   محمد علي "
    app.save()
    assert validate_for_submission(app).is_valid


def test_rule_16_receipt_required(app):
    remove_document(app, D.PAYMENT_RECEIPT)
    assert_error(app, "receipt", 4, "يرجى رفع إيصال الدفع")


def test_rule_17_declaration_accepted(app):
    app.declaration_accepted_at = None
    app.save()
    assert_error(app, "declaration.accepted", 5, "يرجى الموافقة على الإقرار")


def test_stage_form_ignores_receipt_and_acceptance(app):
    remove_document(app, D.PAYMENT_RECEIPT)
    app.declaration_accepted_at = None
    app.save()
    result = validate_for_submission(app, stage="form")
    assert result.errors == []
    assert result.is_valid is True
    # The stepper still shows the receipt step as incomplete.
    assert result.steps[4] is False
    assert result.steps[5] is False


# --- aggregate behaviour ----------------------------------------------------------------------


def test_all_errors_returned_at_once():
    doctor = DoctorFactory(
        full_name="", national_id=None, gender="", birth_year=None, date_of_birth=None,
        phone_number="", syndicate_type="", sub_syndicate="", syndicate_registration_number="",
        syndicate_registration_year=None, governorate="", address="",
    )  # fmt: skip
    app = ApplicationFactory(doctor=doctor, work_status="")
    result = validate_for_submission(app)
    assert result.is_valid is False
    assert len(result.errors) >= 15
    assert {e.step for e in result.errors} == {1, 3, 4, 5}


def test_steps_complete_mapping(app):
    remove_document(app, D.SYNDICATE_ID)
    app.beneficiaries.filter(row_number=1).update(birth_year=None)
    result = validate_for_submission(app)
    assert result.steps == {1: True, 2: False, 3: False, 4: True, 5: True}


def test_as_dict_groups_errors_by_step(app):
    remove_document(app, D.SYNDICATE_ID)
    data = validate_for_submission(app).as_dict()
    assert data["is_valid"] is False
    assert set(data["by_step"]) == {"1", "2", "3", "4", "5"}
    assert data["by_step"]["3"] == [
        {"step": 3, "field": "documents.SYNDICATE_ID", "code": "MISSING_DOCUMENT",
         "message": "يرجى إرفاق صورة كارنيه النقابة"}
    ]  # fmt: skip
    assert data["steps_complete"]["3"] is False
    assert data["errors"] == data["by_step"]["3"]


def test_unknown_birth_governorate_is_a_warning_only(app):
    app.doctor.national_id = app.doctor.national_id[:7] + "99" + app.doctor.national_id[9:]
    result = validate_for_submission(app)
    assert result.is_valid is True
    assert result.warnings == ["كود محافظة الميلاد في الرقم القومي غير معروف"]


def test_cross_application_beneficiary_duplicate_is_a_warning_only(app):
    BeneficiaryFactory(national_id="28803150101242", kinship=Kinship.WIFE, full_name="سارة")
    result = validate_for_submission(app)
    assert result.is_valid is True
    assert len(result.warnings) == 1
