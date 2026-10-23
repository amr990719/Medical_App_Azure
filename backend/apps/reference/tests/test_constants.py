from apps.reference.constants import (
    BIRTH_GOVERNORATE_CODES,
    GOVERNORATES,
    KINSHIP_FEE_KEY,
    ApplicationStatus,
    DocumentType,
    Kinship,
    PaymentStatus,
    SyndicateType,
    WorkStatus,
)


def test_exactly_27_residence_governorates_in_spec_order():
    assert len(GOVERNORATES) == 27
    assert len(set(GOVERNORATES)) == 27
    assert GOVERNORATES[:3] == ["القاهرة", "الجيزة", "الإسكندرية"]
    assert GOVERNORATES[-1] == "سوهاج"


def test_birth_governorate_codes():
    assert BIRTH_GOVERNORATE_CODES["01"] == "القاهرة"
    assert BIRTH_GOVERNORATE_CODES["88"] == "خارج الجمهورية"
    assert len(BIRTH_GOVERNORATE_CODES) == 28


def test_kinship_labels_are_exact():
    assert dict(Kinship.choices) == {
        "MOTHER": "أم",
        "FATHER": "أب",
        "SON_MINOR": "ابن/ابنة (18 سنة أو أقل)",
        "SON_UNIVERSITY": "ابن/ابنة (طالب جامعي)",
        "SON_GRADUATE": "ابن/ابنة (خريج)",
        "DAUGHTER": "ابنة",
        "HUSBAND": "زوج",
        "WIFE": "زوجة",
    }


def test_every_kinship_has_a_fee_key():
    assert set(KINSHIP_FEE_KEY) == set(Kinship)
    assert KINSHIP_FEE_KEY[Kinship.WIFE] == "spouse"
    assert KINSHIP_FEE_KEY[Kinship.SON_GRADUATE] == "grad_son"
    assert KINSHIP_FEE_KEY[Kinship.DAUGHTER] == "child"
    assert KINSHIP_FEE_KEY[Kinship.FATHER] == "parent"


def test_status_labels():
    assert dict(ApplicationStatus.choices) == {
        "DRAFT": "مسودة",
        "SUBMITTED": "مقدم",
        "UNDER_REVIEW": "قيد المراجعة",
        "NEEDS_CORRECTION": "يحتاج تصحيح",
        "APPROVED": "مقبول",
        "REJECTED": "مرفوض",
    }
    assert PaymentStatus.PENDING_REVIEW.label == "بانتظار التأكيد"


def test_enum_labels():
    assert SyndicateType.HUMAN_MEDICINE.label == "بشري"
    assert SyndicateType.VETERINARY.label == "بيطري"
    assert WorkStatus.PENSIONER.label == "معاش"
    assert WorkStatus.DECEASED.label == "متوفى"


def test_document_types_and_labels():
    assert len(DocumentType.values) == 14
    # BENEFICIARY_NATIONAL_ID keeps its value (existing uploads) and is now the FRONT side.
    assert DocumentType.BENEFICIARY_NATIONAL_ID.label == "بطاقة الرقم القومي للمستفيد (وجه)"
    assert DocumentType.BENEFICIARY_NATIONAL_ID_BACK.label == "بطاقة الرقم القومي للمستفيد (ظهر)"
    assert DocumentType.MEMBER_BIRTH_CERTIFICATE.label == (
        "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم"
    )
    assert DocumentType.INSURANCE_PRINT.label == "برينت تأميني"
    assert DocumentType.OTHER.label == "مستند آخر"
