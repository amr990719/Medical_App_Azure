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
    """Supported kinships. Brother/sister/other are intentionally absent (no fee exists).
    The standalone DAUGHTER («ابنة») was removed on 2026-10-28: the combined `ابن/ابنة (...)`
    options cover daughters."""

    MOTHER = "MOTHER", "أم"
    FATHER = "FATHER", "أب"
    SON_MINOR = "SON_MINOR", "ابن/ابنة (18 سنة أو أقل)"
    SON_UNIVERSITY = "SON_UNIVERSITY", "ابن/ابنة (طالب جامعي)"
    SON_GRADUATE = "SON_GRADUATE", "ابن/ابنة (خريج)"
    HUSBAND = "HUSBAND", "زوج"
    WIFE = "WIFE", "زوجة"


class DocumentType(models.TextChoices):
    NATIONAL_ID_FRONT = "NATIONAL_ID_FRONT", "صورة البطاقة (وجه)"
    NATIONAL_ID_BACK = "NATIONAL_ID_BACK", "صورة البطاقة (ظهر)"
    SYNDICATE_ID = "SYNDICATE_ID", "كارنيه النقابة"
    PERSONAL_PHOTO = "PERSONAL_PHOTO", "صورة العضو الأصلي"
    PAYMENT_RECEIPT = "PAYMENT_RECEIPT", "إيصال الدفع"
    # Member-owned, required only while an active MOTHER beneficiary exists (proves the relation).
    MEMBER_BIRTH_CERTIFICATE = (
        "MEMBER_BIRTH_CERTIFICATE",
        "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم",
    )
    # The value predates the back slot; it stays the FRONT so existing uploads remain valid.
    BENEFICIARY_NATIONAL_ID = "BENEFICIARY_NATIONAL_ID", "بطاقة الرقم القومي للمستفيد (وجه)"
    BENEFICIARY_NATIONAL_ID_BACK = (
        "BENEFICIARY_NATIONAL_ID_BACK",
        "بطاقة الرقم القومي للمستفيد (ظهر)",
    )
    BENEFICIARY_PERSONAL_PHOTO = (
        "BENEFICIARY_PERSONAL_PHOTO",
        "صورة شخصية للمستفيد بخلفية بيضاء",
    )
    BIRTH_CERTIFICATE = "BIRTH_CERTIFICATE", "شهادة ميلاد المستفيد"
    MARRIAGE_CERTIFICATE = "MARRIAGE_CERTIFICATE", "شهادة الزواج"
    INSURANCE_PRINT = "INSURANCE_PRINT", "برينت تأميني"
    UNIVERSITY_ID = "UNIVERSITY_ID", "كارنيه الجامعة"
    OTHER = "OTHER", "مستند آخر"
    # Receipt for additional syndicate dues (apps.dues). Never a form slot: each upload is kept
    # as its own row, so it is exempt from the one-active-document-per-slot rule.
    SYNDICATE_DUES_RECEIPT = "SYNDICATE_DUES_RECEIPT", "إيصال سداد مستحقات نقابية"


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


class DuesRequestStatus(models.TextChoices):
    """Additional syndicate dues requested by an admin (apps.dues); separate from the treatment
    fee and `PaymentStatus`."""

    REQUESTED = "REQUESTED", "بانتظار السداد"
    PENDING_REVIEW = "PENDING_REVIEW", "الإيصال قيد المراجعة"
    REJECTED = "REJECTED", "الإيصال مرفوض"
    CONFIRMED = "CONFIRMED", "تم تأكيد السداد"
    CANCELLED = "CANCELLED", "ملغي"


class DuesReceiptStatus(models.TextChoices):
    PENDING_REVIEW = "PENDING_REVIEW", "قيد المراجعة"
    CONFIRMED = "CONFIRMED", "مقبول"
    REJECTED = "REJECTED", "مرفوض"
    CANCELLED = "CANCELLED", "لم يُراجع (أُلغي الطلب)"


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
    Kinship.SON_UNIVERSITY: "child",  # priced like a minor child in every tier (2026-10-29)
    Kinship.SON_GRADUATE: "grad_son",
    Kinship.HUSBAND: "spouse",
    Kinship.WIFE: "spouse",
}

SPOUSE_KINSHIPS = frozenset({Kinship.HUSBAND, Kinship.WIFE})
PARENT_KINSHIPS = frozenset({Kinship.MOTHER, Kinship.FATHER})
CHILD_KINSHIPS = frozenset({Kinship.SON_MINOR, Kinship.SON_UNIVERSITY, Kinship.SON_GRADUATE})

BENEFICIARY_BIRTH_YEAR_MIN = 1920
REGISTRATION_YEAR_MIN = 1950


class NotificationEvent(models.TextChoices):
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED", "استلام الطلب"
    CORRECTION_NEEDED = "CORRECTION_NEEDED", "طلب استكمال بيانات"
    APPROVED = "APPROVED", "قبول الطلب"
    REJECTED = "REJECTED", "رفض الطلب"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED", "تأكيد السداد"
    PAYMENT_RECEIPT_REJECTED = "PAYMENT_RECEIPT_REJECTED", "رفض إيصال السداد"
    DUES_REQUESTED = "DUES_REQUESTED", "طلب مستحقات"
    DUES_CONFIRMED = "DUES_CONFIRMED", "تأكيد سداد المستحقات"
    DUES_RECEIPT_REJECTED = "DUES_RECEIPT_REJECTED", "رفض إيصال المستحقات"
    DUES_CANCELLED = "DUES_CANCELLED", "إلغاء طلب المستحقات"


class NotificationChannel(models.TextChoices):
    WHATSAPP = "WHATSAPP", "واتساب"
    EMAIL = "EMAIL", "البريد الإلكتروني"


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", "في الانتظار"
    SENDING = "SENDING", "جارٍ الإرسال"
    SENT = "SENT", "تم الإرسال"
    DELIVERED = "DELIVERED", "تم التسليم"
    FAILED = "FAILED", "فشل الإرسال"
    EXPIRED = "EXPIRED", "انتهت صلاحيته"
    SUPPRESSED = "SUPPRESSED", "لم يُرسل (وضع الاختبار)"
    SUPERSEDED = "SUPERSEDED", "لم يعد مطلوبًا"
