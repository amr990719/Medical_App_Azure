"""Admin serializers. National IDs are masked (`29•••••••••123`) unless the admin used the
audited "show full" action (`reveal_national_id=1`), which the view passes in the context."""

from rest_framework import serializers

from apps.applications.models import AdminNote, InsuranceApplication
from apps.audit.models import AuditLog
from apps.beneficiaries.api.serializers import required_documents
from apps.beneficiaries.models import Beneficiary
from apps.doctors.models import Doctor
from apps.documents.api.serializers import DocumentSummarySerializer
from apps.reference.constants import ApplicationStatus, PaymentStatus


def _revealed(serializer) -> bool:
    return bool(serializer.context.get("reveal_national_id"))


class AdminDoctorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    masked_national_id = serializers.CharField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            "id", "email", "full_name", "masked_national_id", "date_of_birth", "birth_year",
            "gender", "religion", "phone_number", "syndicate_type", "sub_syndicate",
            "syndicate_registration_number", "syndicate_registration_year",
            "treatment_card_number", "governorate", "neighborhood", "address", "created_at",
        ]  # fmt: skip
        read_only_fields = fields


class AdminApplicationDoctorSerializer(AdminDoctorSerializer):
    national_id = serializers.SerializerMethodField()

    class Meta(AdminDoctorSerializer.Meta):
        fields = [*AdminDoctorSerializer.Meta.fields, "national_id"]
        read_only_fields = fields

    def get_national_id(self, doctor) -> str | None:
        return doctor.national_id if _revealed(self) else None


class AdminBeneficiarySerializer(serializers.ModelSerializer):
    masked_national_id = serializers.CharField(read_only=True)
    national_id = serializers.SerializerMethodField()
    required_documents = serializers.SerializerMethodField()
    documents = DocumentSummarySerializer(many=True, read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            "id", "row_number", "kinship", "full_name", "birth_year", "masked_national_id",
            "national_id", "is_active", "required_documents", "documents",
        ]  # fmt: skip
        read_only_fields = fields

    def get_national_id(self, beneficiary) -> str | None:
        return beneficiary.national_id if _revealed(self) else None

    def get_required_documents(self, beneficiary) -> list[dict]:
        return required_documents(beneficiary)


class AdminApplicationRowSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    masked_national_id = serializers.CharField(source="doctor.masked_national_id", read_only=True)
    syndicate_type = serializers.CharField(source="doctor.syndicate_type", read_only=True)
    sub_syndicate = serializers.CharField(source="doctor.sub_syndicate", read_only=True)
    governorate = serializers.CharField(source="doctor.governorate", read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = InsuranceApplication
        fields = [
            "id", "reference_number", "fiscal_year", "application_type", "doctor_name",
            "masked_national_id", "syndicate_type", "sub_syndicate", "governorate", "status",
            "payment_status", "submitted_at", "total",
        ]  # fmt: skip
        read_only_fields = fields

    def get_total(self, app) -> int | None:
        return (app.fee_snapshot or {}).get("total")


class AdminApplicationDetailSerializer(serializers.ModelSerializer):
    doctor = AdminApplicationDoctorSerializer(read_only=True)
    beneficiaries = AdminBeneficiarySerializer(many=True, read_only=True)
    documents = DocumentSummarySerializer(many=True, read_only=True)
    reviewed_by_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, default=None
    )
    allowed_transitions = serializers.SerializerMethodField()
    beneficiary_warnings = serializers.SerializerMethodField()

    class Meta:
        model = InsuranceApplication
        fields = [
            "id", "fiscal_year", "application_type", "work_status", "status", "payment_status",
            "reference_number", "declaration_name", "declaration_accepted_at", "fee_snapshot",
            "fee_schedule", "review_notes", "reviewed_by_email", "reviewed_at", "submitted_at",
            "created_at", "updated_at", "doctor", "beneficiaries", "documents",
            "allowed_transitions", "beneficiary_warnings",
        ]  # fmt: skip
        read_only_fields = fields

    def get_allowed_transitions(self, app) -> list[str]:
        from apps.applications.services import admin_allowed_transitions

        return admin_allowed_transitions(app)

    def get_beneficiary_warnings(self, app) -> list[str]:
        from apps.beneficiaries.services import beneficiary_warnings

        return [w for b in app.beneficiaries.all() if b.is_active for w in beneficiary_warnings(b)]


class TransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=ApplicationStatus.choices)
    review_notes = serializers.CharField(
        allow_blank=True, required=False, default="", max_length=4000
    )


class PaymentReviewSerializer(serializers.Serializer):
    payment_status = serializers.ChoiceField(choices=PaymentStatus.choices)
    note = serializers.CharField(allow_blank=True, required=False, default="", max_length=4000)


class AdminNoteSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)

    class Meta:
        model = AdminNote
        fields = ["id", "body", "author_email", "created_at"]
        read_only_fields = ["id", "author_email", "created_at"]
        extra_kwargs = {"body": {"max_length": 4000}}


class AuditEntrySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "action", "timestamp", "user_id", "user_email", "object_type", "object_id",
                  "metadata"]  # fmt: skip
        read_only_fields = fields


class AdminStatsSerializer(serializers.Serializer):
    fiscal_year = serializers.IntegerField()
    total = serializers.IntegerField()
    by_status = serializers.DictField(child=serializers.IntegerField())
    by_payment_status = serializers.DictField(child=serializers.IntegerField())
    receipts_pending = serializers.IntegerField()
