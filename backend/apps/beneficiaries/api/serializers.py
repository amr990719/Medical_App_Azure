from rest_framework import serializers

from apps.applications.requirements import beneficiary_requirements
from apps.beneficiaries.models import Beneficiary
from apps.beneficiaries.services import MSG_INVALID_KINSHIP
from apps.common.fields import CollapsedCharField, NationalIdField, YearField
from apps.documents.api.serializers import DocumentSummarySerializer
from apps.reference.constants import WRITABLE_KINSHIP_CHOICES


def required_documents(beneficiary: Beneficiary) -> list[dict]:
    """Document slots for this row, straight from THE rules table (PROMPT.md §15)."""
    return [r.as_dict() for r in beneficiary_requirements(beneficiary)]


class BeneficiarySerializer(serializers.ModelSerializer):
    documents = DocumentSummarySerializer(many=True, read_only=True)
    required_documents = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            "id", "row_number", "kinship", "full_name", "birth_year", "national_id",
            "is_first_time", "is_active", "required_documents", "documents", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_required_documents(self, beneficiary) -> list[dict]:
        return required_documents(beneficiary)


class BeneficiaryWriteSerializer(serializers.Serializer):
    """Draft-level shape checks; the beneficiary service applies the business rules."""

    row_number = serializers.IntegerField(required=False, min_value=1)
    # Retired kinships (DAUGHTER) are not accepted, whatever the row's stored value.
    kinship = serializers.ChoiceField(
        choices=WRITABLE_KINSHIP_CHOICES,
        allow_blank=True,
        required=False,
        error_messages={"invalid_choice": MSG_INVALID_KINSHIP},
    )
    full_name = CollapsedCharField(max_length=200, allow_blank=True, required=False)
    birth_year = YearField()
    national_id = NationalIdField()
    # null = "not answered yet" (allowed in drafts; required for active rows at submission).
    is_first_time = serializers.BooleanField(allow_null=True, required=False)
