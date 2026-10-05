from rest_framework import serializers

from apps.applications.models import InsuranceApplication
from apps.beneficiaries.api.serializers import BeneficiarySerializer
from apps.common.fields import CollapsedCharField
from apps.documents.api.serializers import DocumentSummarySerializer
from apps.reference.constants import ApplicationType, WorkStatus


class ApplicationSerializer(serializers.ModelSerializer):
    """Doctor view of an application. EVERY field is read-only here; the only writable fields
    are in ApplicationUpdateSerializer (PROMPT.md §2.3 #1, §16.2)."""

    declaration_accepted = serializers.SerializerMethodField()
    is_editable = serializers.BooleanField(read_only=True)
    beneficiaries = BeneficiarySerializer(many=True, read_only=True)
    documents = DocumentSummarySerializer(many=True, read_only=True)

    class Meta:
        model = InsuranceApplication
        fields = [
            "id", "fiscal_year", "application_type", "work_status", "status", "payment_status",
            "reference_number", "declaration_name", "declaration_accepted",
            "declaration_accepted_at", "fee_snapshot", "fee_schedule", "review_notes",
            "reviewed_at", "submitted_at", "created_at", "updated_at", "is_editable",
            "beneficiaries", "documents",
        ]  # fmt: skip
        read_only_fields = fields

    def get_declaration_accepted(self, app) -> bool:
        return app.declaration_accepted_at is not None


class ApplicationCreateSerializer(serializers.Serializer):
    application_type = serializers.ChoiceField(
        choices=ApplicationType.choices, default=ApplicationType.FIRST_TIME
    )


class ApplicationUpdateSerializer(serializers.Serializer):
    """The doctor-editable fields. Anything else in the payload is ignored."""

    application_type = serializers.ChoiceField(choices=ApplicationType.choices, required=False)
    work_status = serializers.ChoiceField(
        choices=WorkStatus.choices, allow_blank=True, required=False
    )
    declaration_name = CollapsedCharField(max_length=200, allow_blank=True, required=False)
    declaration_accepted = serializers.BooleanField(required=False)
