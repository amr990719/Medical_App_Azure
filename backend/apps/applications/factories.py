import factory
from django.utils import timezone

from apps.doctors.factories import DoctorFactory
from apps.reference.constants import (
    ApplicationStatus,
    ApplicationType,
    DocumentType,
    Kinship,
    PaymentStatus,
    WorkStatus,
)

from .models import InsuranceApplication


class ApplicationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InsuranceApplication

    doctor = factory.SubFactory(DoctorFactory)
    fiscal_year = 2026
    application_type = ApplicationType.FIRST_TIME
    work_status = WorkStatus.WORKING
    status = ApplicationStatus.DRAFT


def build_submittable_application(**application_fields) -> InsuranceApplication:
    """Worked example 2 (PROMPT.md §17.4), complete and valid for submission:
    male member born 1985, registered 2014, WIFE 1988, SON_MINOR 2015, SON_MINOR 2018, every
    required document — both national-ID sides, every beneficiary's photo, the children's birth
    certificates (below 16), the member photo of a FIRST_TIME application — and the receipt
    uploaded, declaration signed and accepted.
    Expected fee (FY 2026 v3, tier 3): 825 + 1100 + 605 + 605 + (200 + 4 × 175) + 800 = 4835."""
    from apps.beneficiaries.factories import BeneficiaryFactory
    from apps.documents.factories import DocumentFactory

    doctor = application_fields.pop("doctor", None) or DoctorFactory()
    fields = {
        "doctor": doctor,
        "declaration_name": doctor.full_name,
        "declaration_accepted_at": timezone.now(),
        "payment_status": PaymentStatus.PENDING_REVIEW,
        **application_fields,
    }
    app = ApplicationFactory(**fields)
    for doc_type in (
        DocumentType.NATIONAL_ID_FRONT,
        DocumentType.NATIONAL_ID_BACK,
        DocumentType.SYNDICATE_ID,
        DocumentType.PAYMENT_RECEIPT,
    ):
        DocumentFactory(application=app, document_type=doc_type)
    if app.application_type == ApplicationType.FIRST_TIME:
        DocumentFactory(application=app, document_type=DocumentType.PERSONAL_PHOTO)

    wife = BeneficiaryFactory(
        application=app, row_number=1, kinship=Kinship.WIFE, full_name="سارة محمود علي",
        birth_year=1988, national_id="28803150101242",
    )  # fmt: skip
    son = BeneficiaryFactory(
        application=app, row_number=2, kinship=Kinship.SON_MINOR, full_name="عمر أحمد محمد",
        birth_year=2015,
    )  # fmt: skip
    daughter = BeneficiaryFactory(
        application=app, row_number=3, kinship=Kinship.SON_MINOR, full_name="مريم أحمد محمد",
        birth_year=2018,
    )  # fmt: skip
    for doc_type in (
        DocumentType.BENEFICIARY_NATIONAL_ID,
        DocumentType.BENEFICIARY_NATIONAL_ID_BACK,
        DocumentType.MARRIAGE_CERTIFICATE,
        DocumentType.INSURANCE_PRINT,
    ):
        DocumentFactory(application=app, beneficiary=wife, document_type=doc_type)
    for child in (son, daughter):
        DocumentFactory(
            application=app, beneficiary=child, document_type=DocumentType.BIRTH_CERTIFICATE
        )
    for beneficiary in (wife, son, daughter):
        DocumentFactory(
            application=app,
            beneficiary=beneficiary,
            document_type=DocumentType.BENEFICIARY_PERSONAL_PHOTO,
        )
    return app
