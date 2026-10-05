import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.beneficiaries.factories import BeneficiaryFactory
from apps.documents.factories import DocumentFactory
from apps.documents.models import Document
from apps.reference.constants import DocumentType as D

pytestmark = pytest.mark.django_db


def test_second_active_member_document_same_slot_fails():
    doc = DocumentFactory(document_type=D.NATIONAL_ID_FRONT)
    with pytest.raises(IntegrityError):
        DocumentFactory(application=doc.application, document_type=D.NATIONAL_ID_FRONT)


def test_soft_deleted_document_frees_the_slot():
    doc = DocumentFactory(document_type=D.NATIONAL_ID_FRONT, deleted_at=timezone.now())
    DocumentFactory(application=doc.application, document_type=D.NATIONAL_ID_FRONT)


def test_second_active_beneficiary_document_same_slot_fails():
    b = BeneficiaryFactory()
    DocumentFactory(application=b.application, beneficiary=b, document_type=D.BIRTH_CERTIFICATE)
    with pytest.raises(IntegrityError):
        DocumentFactory(application=b.application, beneficiary=b, document_type=D.BIRTH_CERTIFICATE)


def test_same_type_for_two_beneficiaries_is_allowed():
    b1 = BeneficiaryFactory()
    b2 = BeneficiaryFactory(application=b1.application)
    for b in (b1, b2):
        DocumentFactory(application=b.application, beneficiary=b, document_type=D.BIRTH_CERTIFICATE)


def test_member_document_cannot_point_at_a_beneficiary():
    b = BeneficiaryFactory()
    with pytest.raises(IntegrityError):
        DocumentFactory(application=b.application, beneficiary=b, document_type=D.SYNDICATE_ID)


def test_beneficiary_document_needs_a_beneficiary():
    with pytest.raises(IntegrityError):
        DocumentFactory(document_type=D.MARRIAGE_CERTIFICATE, beneficiary=None)


def test_blob_name_is_unique():
    doc = DocumentFactory()
    with pytest.raises(IntegrityError):
        DocumentFactory(
            application=doc.application, blob_name=doc.blob_name, document_type=D.NATIONAL_ID_BACK
        )


def test_default_manager_hides_soft_deleted_documents():
    live = DocumentFactory(document_type=D.NATIONAL_ID_FRONT)
    gone = DocumentFactory(
        application=live.application, document_type=D.NATIONAL_ID_BACK, deleted_at=timezone.now()
    )
    assert list(Document.objects.all()) == [live]
    assert set(Document.all_objects.all()) == {live, gone}
    assert list(live.application.documents.all()) == [live]
