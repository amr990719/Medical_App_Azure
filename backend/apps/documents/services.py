"""Document services (PROMPT.md §18–20): store (replacing the slot), delete, content access.

Upload order: validate the bytes → write the blob under a server-generated name → commit the
metadata in one transaction holding the application row lock. If the transaction fails the blob
is removed; anything left behind (crash between the two) is an orphan the cleanup job deletes.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.applications.access import ensure_editable_by_owner, lock_application
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.exceptions import ValidationFailed
from apps.reference.constants import DocumentType, ScanStatus

from .models import BENEFICIARY_DOCUMENT_TYPES, MEMBER_DOCUMENT_TYPES, Document
from .naming import build_blob_name
from .storage import get_storage
from .validators import validate_upload

MSG_BENEFICIARY_NOT_FOUND = "المستفيد غير موجود في هذا الطلب"
MSG_MEMBER_DOCUMENT_ONLY = "هذا المستند خاص بالعضو ولا يرتبط بمستفيد"
MSG_BENEFICIARY_REQUIRED = "يرجى تحديد المستفيد لهذا المستند"


def soft_delete_documents(documents, *, actor, reason: str, detach: bool = False) -> int:
    """Soft-delete active documents (the blob cleanup job removes the bytes later).

    `detach=True` also clears the beneficiary link so the beneficiary row can be deleted.
    """
    now = timezone.now()
    count = 0
    for document in documents.select_for_update().filter(deleted_at__isnull=True):
        document.deleted_at = now
        update_fields = ["deleted_at"]
        if detach:
            document.beneficiary = None
            update_fields.append("beneficiary")
        document.save(update_fields=update_fields)
        record(
            actor=actor,
            action=AuditAction.DOCUMENT_DELETED,
            obj=document,
            metadata={"reason": reason, "document_type": document.document_type},
        )
        count += 1
    return count


def _resolve_beneficiary(application, document_type: str, beneficiary_id):
    if document_type in MEMBER_DOCUMENT_TYPES:
        if beneficiary_id:
            raise ValidationFailed(fields={"beneficiary_id": [MSG_MEMBER_DOCUMENT_ONLY]})
        return None
    if not beneficiary_id:
        if document_type in BENEFICIARY_DOCUMENT_TYPES:
            raise ValidationFailed(fields={"beneficiary_id": [MSG_BENEFICIARY_REQUIRED]})
        return None  # OTHER may belong to the member
    beneficiary = application.beneficiaries.filter(pk=beneficiary_id).first()
    if beneficiary is None:
        raise ValidationFailed(fields={"beneficiary_id": [MSG_BENEFICIARY_NOT_FOUND]})
    return beneficiary


def store_document(
    application, *, document_type: str, upload, actor, beneficiary_id=None, request=None
) -> Document:
    from apps.applications.services import mark_receipt_uploaded

    document_type = DocumentType(document_type)
    ensure_editable_by_owner(application, actor)  # fail fast, before reading the file
    beneficiary = _resolve_beneficiary(application, document_type, beneficiary_id)
    info = validate_upload(upload, document_type=document_type)

    storage = get_storage()
    blob_name = build_blob_name(
        application.pk, beneficiary.pk if beneficiary else None, document_type, info.extension
    )
    storage.upload(blob_name, info.data, content_type=info.content_type)
    try:
        with transaction.atomic():
            app = lock_application(application.pk)
            ensure_editable_by_owner(app, actor)  # re-check under the lock
            previous = (
                Document.objects.select_for_update()
                .filter(application=app, beneficiary=beneficiary, document_type=document_type)
                .first()
            )
            if previous is not None:
                previous.deleted_at = timezone.now()
                previous.save(update_fields=["deleted_at"])
            document = Document.objects.create(
                application=app,
                beneficiary=beneficiary,
                document_type=document_type,
                blob_name=blob_name,
                original_filename=info.filename,
                content_type=info.content_type,
                file_size=info.size,
                sha256=info.sha256,
                scan_status=(
                    ScanStatus.PENDING if settings.MALWARE_SCAN_ENABLED else ScanStatus.SKIPPED
                ),
                uploaded_by=actor,
            )
            if previous is not None:
                record(
                    actor=actor, action=AuditAction.DOCUMENT_REPLACED, obj=previous,
                    metadata={"document_type": document_type, "replaced_by": str(document.pk)},
                    request=request,
                )  # fmt: skip
            record(
                actor=actor,
                action=AuditAction.DOCUMENT_UPLOADED,
                obj=document,
                metadata={
                    "document_type": document_type,
                    "content_type": info.content_type,
                    "file_size": info.size,
                    "beneficiary_id": str(beneficiary.pk) if beneficiary else None,
                },
                request=request,
            )
            if document_type == DocumentType.PAYMENT_RECEIPT:
                mark_receipt_uploaded(app, actor=actor, request=request)
    except BaseException:
        storage.delete(blob_name)
        raise
    return document


@transaction.atomic
def delete_document(document: Document, *, actor, request=None) -> None:
    from apps.applications.services import mark_receipt_removed

    app = lock_application(document.application_id)
    ensure_editable_by_owner(app, actor)
    soft_delete_documents(Document.objects.filter(pk=document.pk), actor=actor, reason="DELETED")
    if document.document_type == DocumentType.PAYMENT_RECEIPT:
        mark_receipt_removed(app, actor=actor, request=request)


@dataclass(frozen=True)
class DocumentContent:
    redirect_url: str | None = None
    data: bytes = b""
    content_type: str = ""
    filename: str = ""


def document_content(document: Document, *, actor, request=None) -> DocumentContent:
    """Bytes (or a ≤5-minute read-only SAS URL) for an AUTHORIZED caller — the view's queryset
    has already scoped `document` to its owner or to an admin. Every access is audited."""
    storage = get_storage()
    url = None
    if settings.DOCUMENT_CONTENT_DELIVERY == "sas":
        url = storage.read_url(
            document.blob_name,
            ttl_seconds=settings.BLOB_SAS_TTL_SECONDS,
            content_type=document.content_type,
            filename=document.original_filename or "document",
        )
    record(
        actor=actor,
        action=AuditAction.DOCUMENT_VIEWED,
        obj=document,
        metadata={"document_type": document.document_type, "delivery": "sas" if url else "stream"},
        request=request,
    )
    if url:
        return DocumentContent(redirect_url=url)
    return DocumentContent(
        data=storage.download(document.blob_name),
        content_type=document.content_type,
        filename=document.original_filename or "document",
    )


__all__ = [
    "Document",
    "delete_document",
    "document_content",
    "soft_delete_documents",
    "store_document",
]
