import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.reference.constants import DocumentType, ScanStatus

MEMBER_DOCUMENT_TYPES = (
    DocumentType.NATIONAL_ID_FRONT,
    DocumentType.NATIONAL_ID_BACK,
    DocumentType.SYNDICATE_ID,
    DocumentType.PERSONAL_PHOTO,
    DocumentType.PAYMENT_RECEIPT,
)
BENEFICIARY_DOCUMENT_TYPES = (
    DocumentType.BENEFICIARY_NATIONAL_ID,
    DocumentType.BIRTH_CERTIFICATE,
    DocumentType.MARRIAGE_CERTIFICATE,
    DocumentType.INSURANCE_PRINT,
    DocumentType.UNIVERSITY_ID,
)


class ActiveDocumentManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Document(models.Model):
    """Document METADATA (PROMPT.md §19). The bytes live in a private Blob container.

    One active document per (application, beneficiary, document_type); re-upload soft-deletes
    the previous one. Soft-deleted rows are kept for the blob cleanup job and audit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.InsuranceApplication", on_delete=models.PROTECT, related_name="documents"
    )
    beneficiary = models.ForeignKey(
        "beneficiaries.Beneficiary",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    blob_name = models.CharField(max_length=400)  # server-generated, unique (see Meta)
    original_filename = models.CharField(max_length=255, blank=True)  # sanitized, display only
    content_type = models.CharField(max_length=100)  # sniffed server-side
    file_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(
        max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    # Set by `manage.py cleanup_blobs` once the bytes of a soft-deleted document are removed.
    blob_purged_at = models.DateTimeField(null=True, blank=True)

    all_objects = models.Manager()
    objects = ActiveDocumentManager()  # default: active (not soft-deleted) documents only

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        indexes = [
            # The blob cleanup job scans soft-deleted rows only.
            models.Index(
                fields=["deleted_at"],
                condition=Q(deleted_at__isnull=False),
                name="document_deleted_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(fields=["blob_name"], name="uniq_document_blob_name"),
            # NULLS NOT DISTINCT (PostgreSQL 15+): member documents (beneficiary NULL) are also
            # limited to one active row per type.
            models.UniqueConstraint(
                fields=["application", "beneficiary", "document_type"],
                condition=Q(deleted_at__isnull=True),
                nulls_distinct=False,
                name="uniq_active_document_per_slot",
            ),
            # Active documents must match their owner. Soft-deleted beneficiary documents are
            # detached (beneficiary NULL) when the beneficiary row itself is deleted.
            models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=False)
                    | Q(beneficiary__isnull=True, document_type__in=MEMBER_DOCUMENT_TYPES)
                    | Q(beneficiary__isnull=False, document_type__in=BENEFICIARY_DOCUMENT_TYPES)
                    | Q(document_type=DocumentType.OTHER)
                ),
                name="document_type_matches_owner",
            ),
            models.CheckConstraint(
                condition=Q(scan_status__in=ScanStatus.values), name="document_scan_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_type} {self.pk}"
