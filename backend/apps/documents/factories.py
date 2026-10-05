import hashlib

import factory

from apps.applications.factories import ApplicationFactory
from apps.reference.constants import DocumentType, ScanStatus

from .models import Document


class DocumentFactory(factory.django.DjangoModelFactory):
    """Metadata only — no blob is written (storage arrives in Session 3)."""

    class Meta:
        model = Document

    application = factory.SubFactory(ApplicationFactory)
    beneficiary = None
    document_type = DocumentType.NATIONAL_ID_FRONT
    blob_name = factory.Sequence(lambda n: f"applications/test/doctor/document-{n}.jpg")
    original_filename = "scan.jpg"
    content_type = "image/jpeg"
    file_size = 120_000
    sha256 = factory.Sequence(lambda n: hashlib.sha256(str(n).encode()).hexdigest())
    scan_status = ScanStatus.SKIPPED
    uploaded_by = factory.LazyAttribute(lambda o: o.application.doctor.user)
