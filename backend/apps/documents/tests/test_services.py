"""Document services: store (replace slot), delete, content access, audit (PROMPT.md §19, §39)."""

from unittest import mock

import pytest
from django.db import IntegrityError

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.audit.models import AuditAction, AuditLog
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.common.exceptions import (
    ApplicationNotEditable,
    PermissionDeniedError,
    UnsupportedFileType,
    ValidationFailed,
)
from apps.doctors.factories import DoctorFactory
from apps.documents.models import Document
from apps.documents.services import delete_document, document_content, store_document
from apps.documents.storage import get_storage
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import DocumentType as T
from apps.reference.constants import Kinship, PaymentStatus
from tests.files import EXE_BYTES, pdf_bytes, png_upload, upload

pytestmark = pytest.mark.django_db


def blobs() -> list[str]:
    return [b.name for b in get_storage().list("applications/")]


def test_store_member_document_writes_blob_and_metadata():
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.NATIONAL_ID_FRONT, upload=png_upload(name="../بطاقة.png"),
        actor=app.doctor.user,
    )  # fmt: skip
    assert doc.blob_name.startswith(f"applications/{app.pk}/doctor/national-id-front-")
    assert doc.blob_name.endswith(".png")
    assert doc.original_filename == "بطاقة.png"
    assert doc.content_type == "image/png"
    assert doc.uploaded_by == app.doctor.user
    assert get_storage().download(doc.blob_name)[:4] == b"\x89PNG"
    entry = AuditLog.objects.get(action=AuditAction.DOCUMENT_UPLOADED)
    assert entry.object_id == doc.pk
    assert entry.metadata == {
        "document_type": "NATIONAL_ID_FRONT",
        "content_type": "image/png",
        "file_size": doc.file_size,
        "beneficiary_id": None,
    }
    assert "بطاقة" not in str(entry.metadata)  # filenames may hold personal data


def test_scan_status_is_skipped_until_malware_scanning_is_enabled(settings):
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    assert doc.scan_status == "SKIPPED"
    settings.MALWARE_SCAN_ENABLED = True
    doc = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    assert doc.scan_status == "PENDING"


def test_upload_replaces_slot_and_soft_deletes_old():
    app = ApplicationFactory()
    user = app.doctor.user
    first = store_document(app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=user)
    second = store_document(app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=user)
    first.refresh_from_db()
    assert first.deleted_at is not None
    assert list(Document.objects.filter(application=app)) == [second]
    replaced = AuditLog.objects.get(action=AuditAction.DOCUMENT_REPLACED)
    assert replaced.object_id == first.pk
    assert replaced.metadata["replaced_by"] == str(second.pk)
    assert len(blobs()) == 2  # the old blob waits for the cleanup job


def test_receipt_upload_sets_pending_review():
    app = ApplicationFactory()
    store_document(app, document_type=T.PAYMENT_RECEIPT, upload=png_upload(), actor=app.doctor.user)
    app.refresh_from_db()
    assert app.payment_status == PaymentStatus.PENDING_REVIEW
    assert AuditLog.objects.filter(action=AuditAction.PAYMENT_STATUS_CHANGED).count() == 1


def test_beneficiary_document_goes_under_the_beneficiary_prefix():
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app, kinship=Kinship.SON_MINOR)
    doc = store_document(
        app, document_type=T.BIRTH_CERTIFICATE, upload=png_upload(), actor=app.doctor.user,
        beneficiary_id=b.pk,
    )  # fmt: skip
    assert doc.beneficiary == b
    assert doc.blob_name.startswith(
        f"applications/{app.pk}/beneficiaries/{b.pk}/birth-certificate-"
    )


def test_beneficiary_of_another_application_rejected():
    app = ApplicationFactory()
    foreign = BeneficiaryFactory()
    with pytest.raises(ValidationFailed) as exc:
        store_document(
            app, document_type=T.BIRTH_CERTIFICATE, upload=png_upload(), actor=app.doctor.user,
            beneficiary_id=foreign.pk,
        )  # fmt: skip
    assert "beneficiary_id" in exc.value.fields
    assert blobs() == []


@pytest.mark.parametrize(
    ("doc_type", "with_beneficiary"),
    [(T.NATIONAL_ID_FRONT, True), (T.BIRTH_CERTIFICATE, False), (T.PAYMENT_RECEIPT, True)],
)
def test_document_type_must_match_owner(doc_type, with_beneficiary):
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app)
    with pytest.raises(ValidationFailed):
        store_document(
            app, document_type=doc_type, upload=png_upload(), actor=app.doctor.user,
            beneficiary_id=b.pk if with_beneficiary else None,
        )  # fmt: skip


def test_invalid_file_leaves_no_blob_and_no_row():
    app = ApplicationFactory()
    with pytest.raises(UnsupportedFileType):
        store_document(
            app, document_type=T.PAYMENT_RECEIPT, upload=upload(EXE_BYTES, "r.jpg", "image/jpeg"),
            actor=app.doctor.user,
        )  # fmt: skip
    assert blobs() == []
    assert not Document.all_objects.exists()


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.APPROVED, S.REJECTED])
def test_store_refused_when_not_editable(status):
    app = ApplicationFactory(status=status, reference_number="MED-2026-000001")
    with pytest.raises(ApplicationNotEditable):
        store_document(
            app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
        )
    assert blobs() == []


def test_store_by_another_doctor_refused():
    app = ApplicationFactory()
    with pytest.raises(PermissionDeniedError):
        store_document(
            app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=DoctorFactory().user
        )


def test_blob_removed_when_the_database_write_fails():
    app = ApplicationFactory()
    with (
        mock.patch("apps.documents.services.Document.objects.create", side_effect=IntegrityError),
        pytest.raises(IntegrityError),
    ):
        store_document(
            app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
        )
    assert blobs() == []


# --- delete -------------------------------------------------------------------------------------


def test_delete_soft_deletes_and_audits():
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    delete_document(doc, actor=app.doctor.user)
    doc.refresh_from_db()
    assert doc.deleted_at is not None
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_DELETED, object_id=doc.pk).exists()


def test_deleting_the_receipt_resets_payment_status():
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.PAYMENT_RECEIPT, upload=png_upload(), actor=app.doctor.user
    )
    delete_document(doc, actor=app.doctor.user)
    app.refresh_from_db()
    assert app.payment_status == PaymentStatus.NOT_UPLOADED


def test_delete_only_when_editable():
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    app.status, app.reference_number = S.SUBMITTED, "MED-2026-000001"
    app.save()
    with pytest.raises(ApplicationNotEditable):
        delete_document(doc, actor=app.doctor.user)
    doc.refresh_from_db()
    assert doc.deleted_at is None


# --- content ------------------------------------------------------------------------------------


def test_content_streams_bytes_and_audits_view():
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    result = document_content(doc, actor=app.doctor.user)
    assert result.redirect_url is None
    assert result.data[:4] == b"\x89PNG"
    assert result.content_type == "image/png"
    viewed = AuditLog.objects.get(action=AuditAction.DOCUMENT_VIEWED)
    assert viewed.metadata == {"document_type": "SYNDICATE_ID", "delivery": "stream"}


def test_content_by_admin_is_audited_with_the_admin_as_actor():
    app = ApplicationFactory()
    doc = store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )
    admin = AdminUserFactory()
    document_content(doc, actor=admin)
    assert AuditLog.objects.get(action=AuditAction.DOCUMENT_VIEWED).user == admin


# --- beneficiary national ID: separate front and back slots -----------------------------------


def _store(app, doc_type, beneficiary=None, file=None):
    return store_document(
        app, document_type=doc_type, upload=file or png_upload(), actor=app.doctor.user,
        beneficiary_id=beneficiary.pk if beneficiary else None,
    )  # fmt: skip


def test_id_front_and_back_are_independent_slots():
    app = ApplicationFactory()
    wife = BeneficiaryFactory(application=app, kinship=Kinship.WIFE, birth_year=1988)
    front = _store(app, T.BENEFICIARY_NATIONAL_ID, wife)
    back = _store(app, T.BENEFICIARY_NATIONAL_ID_BACK, wife)
    assert set(Document.objects.filter(beneficiary=wife)) == {front, back}
    assert front.blob_name.startswith(f"applications/{app.pk}/beneficiaries/{wife.pk}/national-id-")
    assert back.blob_name.startswith(
        f"applications/{app.pk}/beneficiaries/{wife.pk}/national-id-back-"
    )
    assert not AuditLog.objects.filter(action=AuditAction.DOCUMENT_REPLACED).exists()


def test_replacing_the_back_keeps_an_existing_front_upload():
    app = ApplicationFactory()
    mother = BeneficiaryFactory(application=app, kinship=Kinship.MOTHER, birth_year=1960)
    front = _store(app, T.BENEFICIARY_NATIONAL_ID, mother)  # e.g. uploaded before the back slot
    old_back = _store(app, T.BENEFICIARY_NATIONAL_ID_BACK, mother)
    new_back = _store(app, T.BENEFICIARY_NATIONAL_ID_BACK, mother)
    old_back.refresh_from_db()
    front.refresh_from_db()
    assert old_back.deleted_at is not None
    assert front.deleted_at is None
    assert set(Document.objects.filter(beneficiary=mother)) == {front, new_back}
    replaced = AuditLog.objects.get(action=AuditAction.DOCUMENT_REPLACED)
    assert replaced.object_id == old_back.pk
    assert replaced.metadata["document_type"] == "BENEFICIARY_NATIONAL_ID_BACK"


def test_replacing_the_front_keeps_the_back():
    app = ApplicationFactory()
    wife = BeneficiaryFactory(application=app, kinship=Kinship.WIFE, birth_year=1988)
    old_front = _store(app, T.BENEFICIARY_NATIONAL_ID, wife)
    back = _store(app, T.BENEFICIARY_NATIONAL_ID_BACK, wife)
    new_front = _store(app, T.BENEFICIARY_NATIONAL_ID, wife)
    assert set(Document.objects.filter(beneficiary=wife)) == {new_front, back}
    old_front.refresh_from_db()
    assert old_front.deleted_at is not None


def test_deleting_one_side_leaves_the_other():
    app = ApplicationFactory()
    wife = BeneficiaryFactory(application=app, kinship=Kinship.WIFE, birth_year=1988)
    front = _store(app, T.BENEFICIARY_NATIONAL_ID, wife)
    back = _store(app, T.BENEFICIARY_NATIONAL_ID_BACK, wife)
    delete_document(back, actor=app.doctor.user)
    assert list(Document.objects.filter(beneficiary=wife)) == [front]
    assert AuditLog.objects.get(action=AuditAction.DOCUMENT_DELETED).object_id == back.pk


@pytest.mark.parametrize("doc_type", [T.BENEFICIARY_NATIONAL_ID_BACK, T.BENEFICIARY_PERSONAL_PHOTO])
def test_new_beneficiary_slots_require_a_beneficiary(doc_type):
    app = ApplicationFactory()
    with pytest.raises(ValidationFailed) as exc:
        _store(app, doc_type)
    assert "beneficiary_id" in exc.value.fields
    assert blobs() == []


# --- member birth certificate (proof of the relation to the mother) -------------------------


def test_member_birth_certificate_is_member_owned():
    app = ApplicationFactory()
    doc = _store(app, T.MEMBER_BIRTH_CERTIFICATE)
    assert doc.beneficiary is None
    assert doc.blob_name.startswith(f"applications/{app.pk}/doctor/member-birth-certificate-")
    mother = BeneficiaryFactory(application=app, kinship=Kinship.MOTHER)
    with pytest.raises(ValidationFailed):
        _store(app, T.MEMBER_BIRTH_CERTIFICATE, mother)


def test_member_birth_certificate_survives_when_the_mother_is_removed():
    from apps.beneficiaries.services import delete_beneficiary, update_beneficiary

    app = ApplicationFactory()
    mother = BeneficiaryFactory(application=app, kinship=Kinship.MOTHER, birth_year=1960)
    certificate = _store(app, T.MEMBER_BIRTH_CERTIFICATE)
    update_beneficiary(mother, actor=app.doctor.user, changes={"kinship": Kinship.FATHER})
    assert Document.objects.filter(pk=certificate.pk).exists()
    delete_beneficiary(mother, actor=app.doctor.user)
    assert Document.objects.filter(pk=certificate.pk).exists()  # no longer required, kept


# --- personal photos: images only, even when PDFs are enabled --------------------------------


@pytest.mark.parametrize("doc_type", [T.PERSONAL_PHOTO, T.BENEFICIARY_PERSONAL_PHOTO])
def test_photos_refuse_pdf_even_when_pdfs_are_enabled(settings, doc_type):
    settings.ALLOW_PDF_DOCUMENTS = True
    app = ApplicationFactory()
    son = BeneficiaryFactory(application=app, kinship=Kinship.SON_MINOR)
    owner = son if doc_type == T.BENEFICIARY_PERSONAL_PHOTO else None
    with pytest.raises(UnsupportedFileType):
        _store(app, doc_type, owner, file=upload(pdf_bytes(), "photo.pdf", "application/pdf"))
    assert _store(app, doc_type, owner).content_type == "image/png"


def test_pdf_still_accepted_for_other_beneficiary_documents(settings):
    settings.ALLOW_PDF_DOCUMENTS = True
    app = ApplicationFactory()
    wife = BeneficiaryFactory(application=app, kinship=Kinship.WIFE, birth_year=1988)
    doc = _store(app, T.BENEFICIARY_NATIONAL_ID_BACK, wife,
                 file=upload(pdf_bytes(), "back.pdf", "application/pdf"))  # fmt: skip
    assert doc.content_type == "application/pdf"


def test_member_and_beneficiary_photos_are_distinct_slots():
    app = ApplicationFactory()
    son = BeneficiaryFactory(application=app, kinship=Kinship.SON_MINOR)
    member_photo = _store(app, T.PERSONAL_PHOTO)
    son_photo = _store(app, T.BENEFICIARY_PERSONAL_PHOTO, son)
    assert member_photo.beneficiary is None and son_photo.beneficiary == son
    assert son_photo.blob_name.startswith(
        f"applications/{app.pk}/beneficiaries/{son.pk}/personal-photo-"
    )
    with pytest.raises(ValidationFailed):
        _store(app, T.PERSONAL_PHOTO, son)
