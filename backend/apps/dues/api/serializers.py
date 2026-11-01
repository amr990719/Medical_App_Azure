"""Dues read models. Every field is read-only; the member writes nothing but a file. Who
reviewed, and why an admin cancelled, stay on the admin side."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.fields import MoneyField
from apps.documents.api.serializers import DocumentSummarySerializer
from apps.dues import services
from apps.dues.models import DuesReceipt, SyndicateDuesRequest
from apps.reference.constants import DuesReceiptStatus

RECEIPT_FIELDS = ["id", "status", "rejection_reason", "created_at", "reviewed_at", "document"]
REQUEST_FIELDS = ["id", "amount", "reason", "status", "created_at", "resolved_at", "receipts"]


class DuesReceiptSerializer(serializers.ModelSerializer):
    document = DocumentSummarySerializer(read_only=True)

    class Meta:
        model = DuesReceipt
        fields = RECEIPT_FIELDS
        read_only_fields = fields


class AdminDuesReceiptSerializer(DuesReceiptSerializer):
    reviewed_by_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, default=None, allow_null=True
    )

    class Meta(DuesReceiptSerializer.Meta):
        fields = [*RECEIPT_FIELDS, "reviewed_by_email"]
        read_only_fields = fields


class DuesRequestSerializer(serializers.ModelSerializer):
    """Member view: amount, the admin's explanation, status, own receipts and what is possible."""

    amount = MoneyField(read_only=True)
    receipts = DuesReceiptSerializer(many=True, read_only=True)
    can_upload_receipt = serializers.SerializerMethodField()

    class Meta:
        model = SyndicateDuesRequest
        fields = [*REQUEST_FIELDS, "can_upload_receipt"]
        read_only_fields = fields

    def get_can_upload_receipt(self, dues) -> bool:
        return services.doctor_can_upload(dues)


class AdminDuesRequestSerializer(serializers.ModelSerializer):
    amount = MoneyField(read_only=True)
    receipts = AdminDuesReceiptSerializer(many=True, read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    resolved_by_email = serializers.EmailField(
        source="resolved_by.email", read_only=True, default=None, allow_null=True
    )
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = SyndicateDuesRequest
        fields = [
            *REQUEST_FIELDS, "created_by_email", "resolved_by_email", "cancellation_reason",
            "allowed_actions",
        ]  # fmt: skip
        read_only_fields = fields

    @extend_schema_field(
        serializers.ListField(
            child=serializers.ChoiceField(
                choices=[services.CONFIRM_RECEIPT, services.REJECT_RECEIPT, services.CANCEL]
            )
        )
    )
    def get_allowed_actions(self, dues) -> list[str]:
        return services.admin_dues_actions(dues)


class DuesRequestCreateSerializer(serializers.Serializer):
    amount = MoneyField()
    reason = serializers.CharField(max_length=2000, allow_blank=True)


class DuesReviewSerializer(serializers.Serializer):
    receipt_id = serializers.UUIDField(required=False, allow_null=True)
    decision = serializers.ChoiceField(
        choices=[DuesReceiptStatus.CONFIRMED.value, DuesReceiptStatus.REJECTED.value]
    )
    reason = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")


class DuesCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, allow_blank=True)


class DuesReceiptUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=True, use_url=False)
