import json

import pytest

from apps.reference.constants import DocumentType as D
from apps.reference.constants import Gender, Kinship
from apps.reference.document_rules import (
    DOCUMENT_LABELS,
    OCR_CAPABLE_TYPES,
    beneficiary_document_requirements,
    member_document_requirements,
    rules_as_reference_data,
)

FY = 2026


def required(reqs):
    return {r.document_type for r in reqs if r.required}


def optional(reqs):
    return {r.document_type for r in reqs if not r.required}


def child_reqs(kinship, age, member_gender=Gender.MALE, **kw):
    birth_year = None if age is None else FY - age
    return beneficiary_document_requirements(
        kinship, birth_year, fiscal_year=FY, member_gender=member_gender, **kw
    )


# --- member -----------------------------------------------------------------------------------


def test_member_requirements_default():
    reqs = member_document_requirements(require_photo=False)
    assert required(reqs) == {
        D.NATIONAL_ID_FRONT,
        D.NATIONAL_ID_BACK,
        D.SYNDICATE_ID,
        D.PAYMENT_RECEIPT,
    }
    assert optional(reqs) == {D.PERSONAL_PHOTO}


def test_photo_flag_makes_photo_required():
    reqs = member_document_requirements(require_photo=True)
    assert D.PERSONAL_PHOTO in required(reqs)


def test_receipt_is_a_submit_stage_requirement():
    stages = {r.document_type: r.stage for r in member_document_requirements(require_photo=False)}
    assert stages[D.PAYMENT_RECEIPT] == "submit"
    assert stages[D.NATIONAL_ID_FRONT] == "form"


# --- beneficiaries ----------------------------------------------------------------------------


@pytest.mark.parametrize("kinship", [Kinship.HUSBAND, Kinship.WIFE])
def test_spouse_requires_three_documents(kinship):
    reqs = child_reqs(kinship, 40)
    assert required(reqs) == {D.BENEFICIARY_NATIONAL_ID, D.MARRIAGE_CERTIFICATE, D.INSURANCE_PRINT}


@pytest.mark.parametrize("kinship", [Kinship.MOTHER, Kinship.FATHER])
def test_parent_requires_national_id_only(kinship):
    assert required(child_reqs(kinship, 70)) == {D.BENEFICIARY_NATIONAL_ID}


@pytest.mark.parametrize("kinship", [Kinship.SON_MINOR, Kinship.DAUGHTER])
def test_child_under_16_needs_birth_certificate_and_id_is_optional(kinship):
    reqs = child_reqs(kinship, 15)
    assert required(reqs) == {D.BIRTH_CERTIFICATE}
    assert optional(reqs) == {D.BENEFICIARY_NATIONAL_ID}


@pytest.mark.parametrize("kinship", [Kinship.SON_MINOR, Kinship.DAUGHTER])
def test_child_16_with_male_member_needs_national_id_only(kinship):
    reqs = child_reqs(kinship, 16)
    assert required(reqs) == {D.BENEFICIARY_NATIONAL_ID}
    assert D.BIRTH_CERTIFICATE not in required(reqs)


def test_child_over_16_with_female_member_also_needs_birth_certificate():
    reqs = child_reqs(Kinship.DAUGHTER, 20, member_gender=Gender.FEMALE)
    assert required(reqs) == {D.BENEFICIARY_NATIONAL_ID, D.BIRTH_CERTIFICATE}


def test_unknown_birth_year_is_treated_as_under_16():
    # Review Focus 3: deterministic requirement even without a birth year.
    reqs = child_reqs(Kinship.SON_MINOR, None)
    assert required(reqs) == {D.BIRTH_CERTIFICATE}
    assert optional(reqs) == {D.BENEFICIARY_NATIONAL_ID}


def test_son_university_adds_university_id():
    assert required(child_reqs(Kinship.SON_UNIVERSITY, 20)) == {
        D.BENEFICIARY_NATIONAL_ID,
        D.UNIVERSITY_ID,
    }


def test_son_graduate_adds_insurance_print():
    assert required(child_reqs(Kinship.SON_GRADUATE, 25)) == {
        D.BENEFICIARY_NATIONAL_ID,
        D.INSURANCE_PRINT,
    }


def test_child_age_threshold_is_configurable():
    reqs = child_reqs(Kinship.SON_MINOR, 17, child_id_age=18)
    assert required(reqs) == {D.BIRTH_CERTIFICATE}
    reqs = child_reqs(Kinship.SON_MINOR, 18, child_id_age=18)
    assert required(reqs) == {D.BENEFICIARY_NATIONAL_ID}


def test_requirements_carry_labels_and_ocr_flags():
    reqs = {r.document_type: r for r in child_reqs(Kinship.WIFE, 30)}
    assert reqs[D.MARRIAGE_CERTIFICATE].label == "شهادة الزواج"
    assert reqs[D.BENEFICIARY_NATIONAL_ID].ocr_capable is True
    assert reqs[D.MARRIAGE_CERTIFICATE].ocr_capable is False


def test_no_kinship_means_no_requirements():
    assert (
        beneficiary_document_requirements(None, 2000, fiscal_year=FY, member_gender=Gender.MALE)
        == []
    )


def test_labels_cover_every_document_type():
    assert set(DOCUMENT_LABELS) == set(D)
    assert DOCUMENT_LABELS[D.UNIVERSITY_ID] == "كارنيه الجامعة"


def test_ocr_capable_types():
    assert {
        D.NATIONAL_ID_FRONT,
        D.NATIONAL_ID_BACK,
        D.SYNDICATE_ID,
        D.BENEFICIARY_NATIONAL_ID,
        D.BIRTH_CERTIFICATE,
    } == OCR_CAPABLE_TYPES


def test_reference_data_is_json_serializable_and_complete():
    data = rules_as_reference_data(require_photo=False, child_id_age=16)
    json.dumps(data, ensure_ascii=False)
    assert data["child_national_id_age"] == 16
    assert {d["type"] for d in data["document_types"]} == set(D.values)
    assert set(data["kinships"]) == set(Kinship.values)
    assert data["kinships"]["SON_UNIVERSITY"]["base_rule"] == "child"
    assert data["kinships"]["SON_UNIVERSITY"]["extra_required"] == ["UNIVERSITY_ID"]
    assert [m["type"] for m in data["member"] if m["required"]] == [
        "NATIONAL_ID_FRONT",
        "NATIONAL_ID_BACK",
        "SYNDICATE_ID",
        "PAYMENT_RECEIPT",
    ]
