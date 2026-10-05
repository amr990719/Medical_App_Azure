"""Document metadata services. Upload/replace/content access arrive in Session 3."""

from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import Document


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


__all__ = ["Document", "soft_delete_documents"]
