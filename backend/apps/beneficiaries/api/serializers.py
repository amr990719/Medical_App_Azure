from django.conf import settings
from rest_framework import serializers

from apps.beneficiaries.models import Beneficiary
from apps.common.fields import CollapsedCharField, NationalIdField, YearField
from apps.documents.api.serializers import DocumentSummarySerializer
from apps.reference.constants import Kinship
from apps.reference.document_rules import beneficiary_document_requirements


def required_documents(beneficiary: Beneficiary) -> list[dict]:
    """Document slots for this row, straight from THE rules table (PROMPT.md §15)."""
    application = beneficiary.application
    return [
        r.as_dict()
        for r in beneficiary_document_requirements(
            beneficiary.kinship or None,
            beneficiary.birth_year,
            fiscal_year=application.fiscal_year,
            member_gender=application.doctor.gender or None,
            child_id_age=settings.CHILD_NATIONAL_ID_AGE,
        )
    ]


class BeneficiarySerializer(serializers.ModelSerializer):
    documents = DocumentSummarySerializer(many=True, read_only=True)
    required_documents = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            "id", "row_number", "kinship", "full_name", "birth_year", "national_id",
            "is_active", "required_documents", "documents", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_required_documents(self, beneficiary) -> list[dict]:
        return required_documents(beneficiary)


class BeneficiaryWriteSerializer(serializers.Serializer):
    """Draft-level shape checks; the beneficiary service applies the business rules."""

    row_number = serializers.IntegerField(required=False, min_value=1)
    kinship = serializers.ChoiceField(choices=Kinship.choices, allow_blank=True, required=False)
    full_name = CollapsedCharField(max_length=200, allow_blank=True, required=False)
    birth_year = YearField()
    national_id = NationalIdField()
