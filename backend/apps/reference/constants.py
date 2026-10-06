"""Reference enums and tables (PROMPT.md §12–§16). The frontend receives these through
`GET /api/v1/reference-data/` and never duplicates them."""

from typing import Literal

from django.db import models


class SyndicateType(models.TextChoices):
    HUMAN_MEDICINE = "HUMAN_MEDICINE", "بشري"
    PHARMACY = "PHARMACY", "صيدلي"
    DENTISTRY = "DENTISTRY", "أسنان"
    VETERINARY = "VETERINARY", "بيطري"


class WorkStatus(models.TextChoices):
    WORKING = "WORKING", "يعمل"
    PENSIONER = "PENSIONER", "معاش"
    DECEASED = "DECEASED", "متوفى"


class Gender(models.TextChoices):
    MALE = "MALE", "ذكر"
    FEMALE = "FEMALE", "أنثى"


class Religion(models.TextChoices):
    MUSLIM = "MUSLIM", "مسلم"
    CHRISTIAN = "CHRISTIAN", "مسيحي"


class Kinship(models.TextChoices):
    """Supported kinships. Brother/sister/other are intentionally absent (no fee exists)."""

    MOTHER = "MOTHER", "أم"
    FATHER = "FATHER", "أب"
    SON_MINOR = "SON_MINOR", "ابن (18 سنة أو أقل)"
    SON_UNIVERSITY = "SON_UNIVERSITY", "ابن (طالب جامعي)"
    SON_GRADUATE = "SON_GRADUATE", "ابن (خريج)"
    DAUGHTER = "DAUGHTER", "ابنة"
    HUSBAND = "HUSBAND", "زوج"
    WIFE = "WIFE", "زوجة"


class DocumentType(models.TextChoices):
    NATIONAL_ID_FRONT = "NATIONAL_ID_FRONT", "صورة البطاقة (وجه)"
    NATIONAL_ID_BACK = "NATIONAL_ID_BACK", "صورة البطاقة (ظهر)"
    SYNDICATE_ID = "SYNDICATE_ID", "كارنيه النقابة"
    PERSONAL_PHOTO = "PERSONAL_PHOTO", "صورة العضو الأصلي"
    PAYMENT_RECEIPT = "PAYMENT_RECEIPT", "إيصال الدفع"
    BENEFICIARY_NATIONAL_ID = "BENEFICIARY_NATIONAL_ID", "بطاقة الرقم القومي"
    BIRTH_CERTIFICATE = "BIRTH_CERTIFICATE", "شهادة الميلاد"
    MARRIAGE_CERTIFICATE = "MARRIAGE_CERTIFICATE", "شهادة الزواج"
    INSURANCE_PRINT = "INSURANCE_PRINT", "برينت تأميني"
    UNIVERSITY_ID = "UNIVERSITY_ID", "كارنيه الجامعة"
    OTHER = "OTHER", "مستند آخر"


class ApplicationType(models.TextChoices):
    FIRST_TIME = "FIRST_TIME", "أول مرة"
    ADDITION = "ADDITION", "إضافة"


class ApplicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "مسودة"
    SUBMITTED = "SUBMITTED", "مقدم"
    UNDER_REVIEW = "UNDER_REVIEW", "قيد المراجعة"
    NEEDS_CORRECTION = "NEEDS_CORRECTION", "يحتاج تصحيح"
    APPROVED = "APPROVED", "مقبول"
    REJECTED = "REJECTED", "مرفوض"


class PaymentStatus(models.TextChoices):
    NOT_UPLOADED = "NOT_UPLOADED", "لم يتم رفع الإيصال"
    PENDING_REVIEW = "PENDING_REVIEW", "بانتظار التأكيد"
    CONFIRMED = "CONFIRMED", "مؤكد"
    REJECTED = "REJECTED", "مرفوض"


class ScanStatus(models.TextChoices):
    PENDING = "PENDING", "قيد الفحص"
    CLEAN = "CLEAN", "سليم"
    INFECTED = "INFECTED", "مصاب"
    SKIPPED = "SKIPPED", "لم يتم الفحص"


# Residence governorates — the 27 options of the form select, in PROMPT.md §13 order.
GOVERNORATES: list[str] = [
    "القاهرة", "الجيزة", "الإسكندرية", "الدقهلية", "البحر الأحمر", "البحيرة", "الفيوم",
    "الغربية", "الإسماعيلية", "المنوفية", "المنيا", "القليوبية", "الوادي الجديد", "السويس",
    "أسوان", "أسيوط", "بني سويف", "بورسعيد", "دمياط", "الشرقية", "جنوب سيناء", "كفر الشيخ",
    "مطروح", "الأقصر", "قنا", "شمال سيناء", "سوهاج",
]  # fmt: skip

# Governorate-of-birth codes (national ID digits 8–9). Unknown codes are a warning only.
BIRTH_GOVERNORATE_CODES: dict[str, str] = {
    "01": "القاهرة", "02": "الإسكندرية", "03": "بورسعيد", "04": "السويس", "11": "دمياط",
    "12": "الدقهلية", "13": "الشرقية", "14": "القليوبية", "15": "كفر الشيخ", "16": "الغربية",
    "17": "المنوفية", "18": "البحيرة", "19": "الإسماعيلية", "21": "الجيزة", "22": "بني سويف",
    "23": "الفيوم", "24": "المنيا", "25": "أسيوط", "26": "سوهاج", "27": "قنا", "28": "أسوان",
    "29": "الأقصر", "31": "البحر الأحمر", "32": "الوادي الجديد", "33": "مطروح",
    "34": "شمال سيناء", "35": "جنوب سيناء", "88": "خارج الجمهورية",
}  # fmt: skip

FeeKey = Literal["spouse", "child", "grad_son", "parent"]

KINSHIP_FEE_KEY: dict[Kinship, FeeKey] = {
    Kinship.MOTHER: "parent",
    Kinship.FATHER: "parent",
    Kinship.SON_MINOR: "child",
    Kinship.SON_UNIVERSITY: "grad_son",
    Kinship.SON_GRADUATE: "grad_son",
    Kinship.DAUGHTER: "child",
    Kinship.HUSBAND: "spouse",
    Kinship.WIFE: "spouse",
}

SPOUSE_KINSHIPS = frozenset({Kinship.HUSBAND, Kinship.WIFE})
PARENT_KINSHIPS = frozenset({Kinship.MOTHER, Kinship.FATHER})
CHILD_KINSHIPS = frozenset(
    {Kinship.SON_MINOR, Kinship.SON_UNIVERSITY, Kinship.SON_GRADUATE, Kinship.DAUGHTER}
)

BENEFICIARY_BIRTH_YEAR_MIN = 1920
REGISTRATION_YEAR_MIN = 1950
