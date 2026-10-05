from django.urls import reverse
from rest_framework import serializers

from apps.documents.models import Document


class DocumentSummarySerializer(serializers.ModelSerializer):
    """Document metadata. Never the blob name or a storage URL: content is served only through
    the authorized `/documents/{id}/content/` endpoint."""

    beneficiary_id = serializers.UUIDField(read_only=True, allow_null=True)
    content_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id", "document_type", "beneficiary_id", "original_filename", "content_type",
            "file_size", "scan_status", "created_at", "content_url",
        ]  # fmt: skip
        read_only_fields = fields

    def get_content_url(self, document) -> str:
        return reverse("document-content", kwargs={"pk": document.pk})
