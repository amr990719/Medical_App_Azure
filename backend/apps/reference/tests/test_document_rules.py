import json

import pytest

from apps.reference.constants import CHILD_KINSHIPS, ApplicationType, Gender, Kinship
from apps.reference.constants import DocumentType as D
from apps.reference.document_rules import (
    DOCUMENT_LABELS,
    HINT_CHILD_BIRTH_CERTIFICATE_UNDER_AGE,
    HINT_FEMALE_MEMBER_BIRTH_CERTIFICATE,
    HINT_PHOTO,
    HINT_PHOTO_CHILD_EXEMPT,
    IMAGE_ONLY_TYPES,
    OCR_CAPABLE_TYPES,
    beneficiary_document_requirements,
    member_document_requirements,
    rules_as_reference_data,
)

FY = 2026
ID_SIDES = {D.BENEFICIARY_NATIONAL_ID, D.BENEFICIARY_NATIONAL_ID_BACK}
PHOTO = D.BENEFICIARY_PERSONAL_PHOTO


def required(reqs):
    return {r.document_type for r in reqs if r.required}


def optional(reqs):
    return {r.document_type for r in reqs if not r.required}


def reqs_for(kinship, age, member_gender=Gender.MALE, **kw):
    birth_year = None if age is None else FY - age
    return beneficiary_document_requirements(
        kinship, birth_year, fiscal_year=FY, member_gender=member_gender, **kw
    )


def by_type(reqs):
    return {r.document_type: r for r in reqs}


# --- member -----------------------------------------------------------------------------------


def test_member_requirements_default():
    # Without an application (reference data) the photo is listed as optional: it depends on
    # the application type (member_conditional).
    reqs = member_document_requirements()
    assert required(reqs) == {
        D.NATIONAL_ID_FRONT,
        D.NATIONAL_ID_BACK,
        D.SYNDICATE_ID,
        D.PAYMENT_RECEIPT,
    }
    assert optional(reqs) == {D.PERSONAL_PHOTO}


def test_first_time_application_requires_the_member_photo():
    reqs = by_type(member_document_requirements(application_type=ApplicationType.FIRST_TIME))
    assert reqs[D.PERSONAL_PHOTO].required is True
    assert reqs[D.PERSONAL_PHOTO].images_only is True


@pytest.mark.parametrize("application_type", [ApplicationType.ADDITION, "", None])
def test_member_photo_is_optional_unless_first_time(application_type):
    reqs = by_type(member_document_requirements(application_type=application_type))
    assert reqs[D.PERSONAL_PHOTO].required is False  # still offered: an upload stays attached


def test_receipt_is_a_submit_stage_requirement():
    stages = {r.document_type: r.stage for r in member_document_requirements()}
    assert stages[D.PAYMENT_RECEIPT] == "submit"
    assert stages[D.NATIONAL_ID_FRONT] == "form"


def test_member_birth_certificate_required_only_with_an_active_mother():
    with_mother = by_type(member_document_requirements(has_active_mother=True))
    slot = with_mother[D.MEMBER_BIRTH_CERTIFICATE]
    assert slot.required is True
    assert slot.label == "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم"
    assert slot.ocr_capable is False  # its OCR must never fill the mother's row
    assert slot.hints
    without = member_document_requirements()
    assert D.MEMBER_BIRTH_CERTIFICATE not in by_type(without)


def test_uploaded_member_birth_certificate_stays_visible_as_optional():
    reqs = member_document_requirements(has_member_birth_certificate=True)
    assert by_type(reqs)[D.MEMBER_BIRTH_CERTIFICATE].required is False


def test_member_birth_certificate_is_distinct_from_the_childs():
    assert D.MEMBER_BIRTH_CERTIFICATE != D.BIRTH_CERTIFICATE
    assert DOCUMENT_LABELS[D.MEMBER_BIRTH_CERTIFICATE] != DOCUMENT_LABELS[D.BIRTH_CERTIFICATE]


# --- beneficiaries: national ID front + back -------------------------------------------------


@pytest.mark.parametrize("kinship", [Kinship.HUSBAND, Kinship.WIFE])
def test_spouse_requires_both_id_sides_marriage_insurance_print_and_photo(kinship):
    assert required(reqs_for(kinship, 40)) == ID_SIDES | {
        D.MARRIAGE_CERTIFICATE,
        D.INSURANCE_PRINT,
        PHOTO,
    }


@pytest.mark.parametrize("kinship", [Kinship.MOTHER, Kinship.FATHER])
def test_parent_requires_both_id_sides_and_photo(kinship):
    reqs = reqs_for(kinship, 70)
    assert required(reqs) == ID_SIDES | {PHOTO}
    assert D.BIRTH_CERTIFICATE not in by_type(reqs)  # the MEMBER's certificate is a member slot


def test_male_member_child_under_16_needs_only_the_birth_certificate_and_photo():
    reqs = reqs_for(Kinship.SON_MINOR, 15)
    assert required(reqs) == {D.BIRTH_CERTIFICATE, PHOTO}
    assert optional(reqs) == ID_SIDES


def test_child_16_with_male_member_needs_both_id_sides_and_photo():
    reqs = reqs_for(Kinship.SON_MINOR, 16)
    assert required(reqs) == ID_SIDES | {PHOTO}
    assert by_type(reqs)[D.BIRTH_CERTIFICATE].required is False  # offered, never lost


def test_unknown_birth_year_is_treated_as_under_16():
    # Review Focus 3: deterministic requirement even without a birth year.
    reqs = reqs_for(Kinship.SON_MINOR, None)
    assert required(reqs) == {D.BIRTH_CERTIFICATE, PHOTO}
    assert optional(reqs) == ID_SIDES
    female = reqs_for(Kinship.SON_MINOR, None, member_gender=Gender.FEMALE)
    assert required(female) == {D.BIRTH_CERTIFICATE, PHOTO}


def test_son_university_adds_university_id():
    assert required(reqs_for(Kinship.SON_UNIVERSITY, 20)) == ID_SIDES | {D.UNIVERSITY_ID, PHOTO}
    assert required(reqs_for(Kinship.SON_UNIVERSITY, 15)) == {D.UNIVERSITY_ID, PHOTO}


def test_son_graduate_adds_insurance_print():
    assert required(reqs_for(Kinship.SON_GRADUATE, 25)) == ID_SIDES | {D.INSURANCE_PRINT, PHOTO}
    assert required(reqs_for(Kinship.SON_GRADUATE, 15)) == {D.INSURANCE_PRINT, PHOTO}


def test_child_age_threshold_is_configurable():
    assert required(reqs_for(Kinship.SON_MINOR, 17, child_id_age=18)) == {
        D.BIRTH_CERTIFICATE,
        PHOTO,
    }
    assert required(reqs_for(Kinship.SON_MINOR, 18, child_id_age=18)) == ID_SIDES | {PHOTO}
    female = reqs_for(Kinship.SON_MINOR, 17, member_gender=Gender.FEMALE, child_id_age=18)
    assert required(female) == {D.BIRTH_CERTIFICATE, PHOTO}


def test_id_sides_are_separate_slots_with_their_own_labels():
    slots = by_type(reqs_for(Kinship.WIFE, 30))
    front, back = slots[D.BENEFICIARY_NATIONAL_ID], slots[D.BENEFICIARY_NATIONAL_ID_BACK]
    assert front.label == "بطاقة الرقم القومي للمستفيد (وجه)"
    assert back.label == "بطاقة الرقم القومي للمستفيد (ظهر)"
    assert (front.ocr_capable, back.ocr_capable) == (True, False)


# --- female member: every child needs a birth certificate, whatever the age -------------------


@pytest.mark.parametrize("kinship", sorted(CHILD_KINSHIPS))
@pytest.mark.parametrize("age", [2, 10, 16, 20, 30, None])
def test_female_member_children_always_need_a_birth_certificate(kinship, age):
    reqs = by_type(reqs_for(kinship, age, member_gender=Gender.FEMALE))
    certificate = reqs[D.BIRTH_CERTIFICATE]
    assert certificate.required is True
    assert certificate.hints == (HINT_FEMALE_MEMBER_BIRTH_CERTIFICATE,)
    older = age is not None and age >= 16
    assert all(reqs[t].required is older for t in ID_SIDES)  # both sides from 16, in addition


def test_female_member_older_children_keep_their_kinship_documents():
    assert required(reqs_for(Kinship.SON_UNIVERSITY, 20, member_gender=Gender.FEMALE)) == (
        ID_SIDES | {D.BIRTH_CERTIFICATE, D.UNIVERSITY_ID, PHOTO}
    )
    assert required(reqs_for(Kinship.SON_GRADUATE, 25, member_gender=Gender.FEMALE)) == (
        ID_SIDES | {D.BIRTH_CERTIFICATE, D.INSURANCE_PRINT, PHOTO}
    )
    assert required(reqs_for(Kinship.SON_MINOR, 17, member_gender=Gender.FEMALE)) == (
        ID_SIDES | {D.BIRTH_CERTIFICATE, PHOTO}
    )


# --- male member: the minor child's birth certificate is required below 16 --------------------


@pytest.mark.parametrize(
    ("age", "needed"),
    [(0, True), (2, True), (15, True), (16, False), (17, False), (18, False), (None, True)],
)
def test_male_member_minor_child_needs_the_birth_certificate_below_16(age, needed):
    reqs = by_type(reqs_for(Kinship.SON_MINOR, age, member_gender=Gender.MALE))
    certificate = reqs[D.BIRTH_CERTIFICATE]
    assert certificate.required is needed  # always offered: an upload stays visible from 16
    assert certificate.hints == ((HINT_CHILD_BIRTH_CERTIFICATE_UNDER_AGE,) if needed else ())
    older = age is not None and age >= 16
    assert all(reqs[t].required is older for t in ID_SIDES)  # the ID rule is unchanged


@pytest.mark.parametrize("kinship", [Kinship.SON_UNIVERSITY, Kinship.SON_GRADUATE])
@pytest.mark.parametrize("age", [15, 16, 20, 30])
def test_male_member_other_child_kinships_keep_the_certificate_optional(kinship, age):
    reqs = by_type(reqs_for(kinship, age, member_gender=Gender.MALE))
    assert reqs[D.BIRTH_CERTIFICATE].required is False
    assert reqs[D.BIRTH_CERTIFICATE].hints == ()


def test_under_age_hint_names_the_configured_threshold():
    assert HINT_CHILD_BIRTH_CERTIFICATE_UNDER_AGE == (
        "شهادة ميلاد الابن/الابنة مطلوبة لمن هم أقل من 16 سنة."
    )
    reqs = by_type(reqs_for(Kinship.SON_MINOR, 16, child_id_age=18))
    assert reqs[D.BIRTH_CERTIFICATE].required is True
    assert reqs[D.BIRTH_CERTIFICATE].hints == (
        "شهادة ميلاد الابن/الابنة مطلوبة لمن هم أقل من 18 سنة.",
    )


@pytest.mark.parametrize(("age", "needed"), [(5, True), (15, True), (16, False)])
def test_unknown_member_gender_minor_child(age, needed):
    reqs = by_type(reqs_for(Kinship.SON_MINOR, age, member_gender=None))
    assert reqs[D.BIRTH_CERTIFICATE].required is needed


def test_birth_certificate_follows_the_members_gender_not_the_childs():
    # From 16: a child of a male member: optional; a child of a female member: required.
    assert by_type(reqs_for(Kinship.SON_MINOR, 17))[D.BIRTH_CERTIFICATE].required is False
    son = reqs_for(Kinship.SON_MINOR, 17, member_gender=Gender.FEMALE)
    assert by_type(son)[D.BIRTH_CERTIFICATE].required is True


def test_female_member_hint_is_kept_below_16():
    reqs = by_type(reqs_for(Kinship.SON_MINOR, 5, member_gender=Gender.FEMALE))
    assert reqs[D.BIRTH_CERTIFICATE].hints == (HINT_FEMALE_MEMBER_BIRTH_CERTIFICATE,)


# --- personal photo for every beneficiary ---------------------------------------------------


@pytest.mark.parametrize("kinship", list(Kinship))
def test_every_beneficiary_of_any_kinship_needs_a_photo(kinship):
    age = 30 if kinship not in CHILD_KINSHIPS else 10
    assert PHOTO in required(reqs_for(kinship, age))


def test_first_time_answer_is_no_longer_an_input():
    with pytest.raises(TypeError):
        reqs_for(Kinship.WIFE, 30, is_first_time=False)


@pytest.mark.parametrize(("age", "needed"), [(0, False), (2, False), (3, True), (4, True)])
@pytest.mark.parametrize("kinship", sorted(CHILD_KINSHIPS))
def test_children_under_3_need_no_photo(kinship, age, needed):
    assert (PHOTO in required(reqs_for(kinship, age))) is needed
    assert PHOTO in by_type(reqs_for(kinship, age))  # always offered


@pytest.mark.parametrize("kinship", [k for k in Kinship if k not in CHILD_KINSHIPS])
def test_a_young_age_never_exempts_other_kinships(kinship):
    assert PHOTO in required(reqs_for(kinship, 2))


def test_unknown_age_never_grants_the_photo_exemption():
    assert PHOTO in required(reqs_for(Kinship.SON_MINOR, None))


def test_photo_exemption_age_is_configurable():
    assert PHOTO not in required(reqs_for(Kinship.SON_MINOR, 3, photo_exempt_child_age=4))


def test_photo_slot_is_image_only_and_has_its_guidance():
    son = by_type(reqs_for(Kinship.SON_MINOR, 5))[PHOTO]
    assert son.images_only is True
    assert son.label == "صورة شخصية للمستفيد بخلفية بيضاء"
    assert son.hints == (HINT_PHOTO, HINT_PHOTO_CHILD_EXEMPT)
    assert HINT_PHOTO == "صورة شخصية بخلفية بيضاء مطلوبة لكل مستفيد."
    assert HINT_PHOTO_CHILD_EXEMPT == "لا تُطلب صورة شخصية للأطفال أقل من 3 سنوات."


@pytest.mark.parametrize("kinship", [k for k in Kinship if k != Kinship.SON_MINOR])
def test_child_exemption_note_is_shown_only_for_son_minor(kinship):
    assert by_type(reqs_for(kinship, 5))[PHOTO].hints == (HINT_PHOTO,)


def test_member_and_beneficiary_photos_are_distinct_image_only_slots():
    assert {D.PERSONAL_PHOTO, PHOTO} == IMAGE_ONLY_TYPES
    assert PHOTO not in by_type(
        member_document_requirements(application_type=ApplicationType.FIRST_TIME)
    )
    assert D.PERSONAL_PHOTO not in by_type(reqs_for(Kinship.WIFE, 30))


# --- shared -----------------------------------------------------------------------------------


def test_requirements_carry_labels_and_ocr_flags():
    reqs = by_type(reqs_for(Kinship.WIFE, 30))
    assert reqs[D.MARRIAGE_CERTIFICATE].label == "شهادة الزواج"
    assert reqs[D.BENEFICIARY_NATIONAL_ID].ocr_capable is True
    assert reqs[D.MARRIAGE_CERTIFICATE].ocr_capable is False


def test_requirement_dict_shape():
    data = by_type(reqs_for(Kinship.SON_MINOR, 5))[PHOTO].as_dict()
    assert set(data) == {"type", "required", "label", "ocr_capable", "stage", "images_only",
                         "hints"}  # fmt: skip
    assert data["images_only"] is True
    assert data["hints"] == [HINT_PHOTO, HINT_PHOTO_CHILD_EXEMPT]


def test_no_kinship_means_no_requirements():
    assert (
        beneficiary_document_requirements(None, 2000, fiscal_year=FY, member_gender=Gender.MALE)
        == []
    )


def test_labels_cover_every_document_type():
    assert set(DOCUMENT_LABELS) == set(D)
    assert DOCUMENT_LABELS[D.UNIVERSITY_ID] == "كارنيه الجامعة"


def test_ocr_capable_types_have_a_working_extraction():
    from apps.ocr.schemas import SCHEMAS

    assert {
        D.NATIONAL_ID_FRONT,
        D.NATIONAL_ID_BACK,
        D.SYNDICATE_ID,
        D.BENEFICIARY_NATIONAL_ID,
        D.BIRTH_CERTIFICATE,
    } == OCR_CAPABLE_TYPES
    assert set(SCHEMAS) == OCR_CAPABLE_TYPES


def test_reference_data_is_json_serializable_and_complete():
    data = rules_as_reference_data(child_id_age=16)
    json.dumps(data, ensure_ascii=False)
    assert data["child_national_id_age"] == 16
    assert data["photo_exempt_child_age"] == 3
    assert {d["type"] for d in data["document_types"]} == set(D.values)
    images_only = {d["type"] for d in data["document_types"] if d["images_only"]}
    assert images_only == {"PERSONAL_PHOTO", "BENEFICIARY_PERSONAL_PHOTO"}
    assert set(data["kinships"]) == set(Kinship.values)
    assert data["kinships"]["SON_UNIVERSITY"]["base_rule"] == "child"
    assert data["kinships"]["SON_UNIVERSITY"]["extra_required"] == ["UNIVERSITY_ID"]
    assert data["base_rules"]["parent"]["required"] == [
        "BENEFICIARY_NATIONAL_ID",
        "BENEFICIARY_NATIONAL_ID_BACK",
    ]
    assert data["member_conditional"] == {
        "PERSONAL_PHOTO": {"required_with_application_type": "FIRST_TIME"},
        "MEMBER_BIRTH_CERTIFICATE": {"required_with_kinship": "MOTHER"},
    }
    child = data["base_rules"]["child"]
    assert child["below_age"] == {
        "required": [],
        "optional": ["BENEFICIARY_NATIONAL_ID", "BENEFICIARY_NATIONAL_ID_BACK"],
    }
    assert child["birth_certificate"] == {
        "type": "BIRTH_CERTIFICATE",
        "required_when_member_gender": "FEMALE",
        "required_below_age_for_kinships": ["SON_MINOR"],
        "otherwise": "optional",
    }
    assert data["photo"] == {
        "type": "BENEFICIARY_PERSONAL_PHOTO",
        "required_when": "always",
        "exempt_child_below_age": 3,
        "unknown_age_exempt": False,
    }
    assert [m["type"] for m in data["member"] if m["required"]] == [
        "NATIONAL_ID_FRONT",
        "NATIONAL_ID_BACK",
        "SYNDICATE_ID",
        "PAYMENT_RECEIPT",
    ]
