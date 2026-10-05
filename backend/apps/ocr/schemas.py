"""Extraction prompts and JSON schemas per document type (PROMPT.md §21.3).

Arabic prompts ported from the prototype's OcrService.js; keys renamed to snake_case. The
schemas describe the RAW provider output (structured outputs in Session 7); `services`
normalizes it into the §21.3 suggestion fields. Prompts contain no personal data.
"""

from dataclasses import dataclass

from apps.reference.constants import DocumentType as T


@dataclass(frozen=True)
class ExtractionSchema:
    name: str
    prompt: str
    properties: tuple[str, ...]

    def json_schema(self) -> dict:
        return {
            "name": self.name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {p: {"type": "string"} for p in self.properties},
                "required": list(self.properties),
                "additionalProperties": False,
            },
        }


NATIONAL_ID_FRONT = ExtractionSchema(
    name="national_id_front",
    prompt=(
        "هذه صورة للوجه الأمامي لبطاقة الرقم القومي المصرية.\n"
        "استخرج البيانات التالية:\n"
        "- member_name: الاسم الكامل للشخص (الاسم الأول + سلسلة الأسماء)\n"
        "- national_id: رقم الهوية المكون من 14 رقماً (أرقام غربية 0-9 فقط، بدون مسافات)\n"
        "- governorate: اسم المحافظة (الجزء بعد الشرطة في سطر العنوان)\n"
        "- address: عنوان الشارع (السطر الذي يحتوي على رقم المبنى والشارع)\n"
        "- neighborhood: اسم الحي أو المنطقة (الجزء قبل الشرطة في السطر الأخير قبل الرقم القومي)\n"
        "ملاحظات: الرقم القومي في الأسفل، يبدأ بـ 2 أو 3، طوله 14 رقماً. "
        "لا توجد تسميات على البطاقة — البيانات في مواضع ثابتة. "
        "اترك الحقل فارغاً إذا لم يكن واضحاً."
    ),
    properties=("member_name", "national_id", "governorate", "address", "neighborhood"),
)

NATIONAL_ID_BACK = ExtractionSchema(
    name="national_id_back",
    prompt=(
        "هذه صورة للوجه الخلفي لبطاقة الرقم القومي المصرية.\n"
        "استخرج البيانات التالية:\n"
        "- gender: ذكر أو أنثى\n"
        "- religion: مسلم أو مسيحي\n"
        "اترك الحقل فارغاً إذا لم يكن واضحاً."
    ),
    properties=("gender", "religion"),
)

SYNDICATE_ID = ExtractionSchema(
    name="syndicate_id",
    prompt=(
        "هذه صورة لكارنيه النقابة الطبية المصرية.\n"
        "تخطيط البطاقة: كل سطر يحتوي على اسم الحقل على اليمين والقيمة على اليسار، مثل:\n"
        "  رقم القيد        : ٣٠٥٧٧٧\n"
        "  تاريخ القيد      : ٢٠٢١-٠٤-٢٨\n"
        "  النقابه الفرعيه  : الجيزة\n"
        "ونوع الطبيب (بشري / صيدلي / أسنان / بيطري) مكتوب في شريط العنوان العلوي للبطاقة.\n"
        "استخرج البيانات التالية:\n"
        "- registration_number: القيمة بجانب 'رقم القيد' — أرقام فقط\n"
        "- sub_syndicate: القيمة بجانب 'النقابه الفرعيه' أو 'النقابة الفرعية'\n"
        "- registration_date: القيمة الكاملة بجانب 'تاريخ القيد' كما هي مكتوبة تماماً\n"
        "- syndicate_type: نوع الطبيب من شريط العنوان: بشري أو صيدلي أو أسنان أو بيطري\n"
        "أرجع قيمة registration_date كما هي على البطاقة بدون أي تحويل."
    ),
    properties=("registration_number", "sub_syndicate", "registration_date", "syndicate_type"),
)

BENEFICIARY_DOCUMENT = ExtractionSchema(
    name="beneficiary_document",
    prompt=(
        "هذه صورة لمستند رسمي (قد يكون بطاقة رقم قومي أو شهادة ميلاد).\n"
        "استخرج البيانات الخاصة بالشخص صاحب المستند (أو الطفل في حالة شهادة الميلاد):\n"
        "- full_name: الاسم بالكامل كما هو مكتوب\n"
        "- national_id: رقم الهوية المكون من 14 رقماً (أرقام غربية 0-9 فقط، بدون مسافات)\n"
        "- birth_date: تاريخ الميلاد المكتوب على المستند\n"
        "اترك الحقل فارغاً إذا لم يكن مكتوباً على المستند."
    ),
    properties=("full_name", "national_id", "birth_date"),
)

SCHEMAS: dict[T, ExtractionSchema] = {
    T.NATIONAL_ID_FRONT: NATIONAL_ID_FRONT,
    T.NATIONAL_ID_BACK: NATIONAL_ID_BACK,
    T.SYNDICATE_ID: SYNDICATE_ID,
    T.BENEFICIARY_NATIONAL_ID: BENEFICIARY_DOCUMENT,
    T.BIRTH_CERTIFICATE: BENEFICIARY_DOCUMENT,
}
