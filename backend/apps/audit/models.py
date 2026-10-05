import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditAction(models.TextChoices):
    APPLICATION_CREATED = "APPLICATION_CREATED"
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_RESUBMITTED = "APPLICATION_RESUBMITTED"
    APPLICATION_STATUS_CHANGED = "APPLICATION_STATUS_CHANGED"
    PAYMENT_STATUS_CHANGED = "PAYMENT_STATUS_CHANGED"
    FEE_SNAPSHOT_CREATED = "FEE_SNAPSHOT_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_REPLACED = "DOCUMENT_REPLACED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    DOCUMENT_VIEWED = "DOCUMENT_VIEWED"
    OCR_REQUESTED = "OCR_REQUESTED"
    ADMIN_APPLICATION_VIEWED = "ADMIN_APPLICATION_VIEWED"
    ADMIN_NOTE_ADDED = "ADMIN_NOTE_ADDED"
    FEE_SCHEDULE_CHANGED = "FEE_SCHEDULE_CHANGED"
    ADMIN_ROLE_GRANTED = "ADMIN_ROLE_GRANTED"
    NATIONAL_ID_REVEALED = "NATIONAL_ID_REVEALED"  # admin "show full" action (§44)


class AuditLog(models.Model):
    """Append-only audit trail (PROMPT.md §39).

    The ORM refuses updates/deletes, and a database trigger (migration 0002) refuses them for
    any client. Metadata holds IDs and changed field names, never sensitive values.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # NULL for system actions (management commands, jobs). PROTECT: users are never erased
    # from the trail.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,  # covered by audit_user_idx (user_id, timestamp)
    )
    action = models.CharField(max_length=40, choices=AuditAction.choices)
    object_type = models.CharField(max_length=64)
    object_id = models.UUIDField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    ip_hash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["object_type", "object_id", "timestamp"], name="audit_object_idx"),
            models.Index(fields=["action", "timestamp"], name="audit_action_idx"),
            models.Index(fields=["user", "timestamp"], name="audit_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("AuditLog is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("AuditLog is append-only.")
