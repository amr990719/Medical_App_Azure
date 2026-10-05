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
from tests.files import EXE_BYTES, png_upload, upload

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
