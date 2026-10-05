from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin
from apps.applications.api.views import UUID_REGEX
from apps.fees.models import FeeSchedule, validate_tier_boundaries, validate_tier_fees
from apps.fees.services import create_schedule_version

MSG_TIER_FEES = "يجب تحديد رسوم صحيحة غير سالبة (أعداد صحيحة) لكل الفئات في الشرائح 1-4"
MSG_BOUNDARIES = "حدود الشرائح يجب أن تكون ثلاثة أعداد صحيحة تصاعدية"


class FeeScheduleSerializer(serializers.ModelSerializer):
    tier_fees = serializers.JSONField()
    tier_boundaries = serializers.JSONField(required=False, default=[5, 10, 15])

    class Meta:
        model = FeeSchedule
        fields = [
            "id", "fiscal_year", "version", "tier_fees", "tier_boundaries",
            "admin_fee_member_only", "admin_fee_with_beneficiaries", "age_cap_threshold",
            "age_cap_amount", "registration_year_min", "is_active", "created_at", "locked_at",
        ]  # fmt: skip
        read_only_fields = ["id", "version", "is_active", "created_at", "locked_at"]
        # Versioning (not a unique check) decides which schedule is active: see the service.
        validators: list = []
        extra_kwargs = {"fiscal_year": {"min_value": 2000, "max_value": 2100, "validators": []}}

    def validate_tier_fees(self, value):
        from django.core.exceptions import ValidationError

        try:
            validate_tier_fees(value)
        except ValidationError:
            raise serializers.ValidationError(MSG_TIER_FEES) from None
        return value

    def validate_tier_boundaries(self, value):
        from django.core.exceptions import ValidationError

        try:
            validate_tier_boundaries(value)
        except ValidationError:
            raise serializers.ValidationError(MSG_BOUNDARIES) from None
        return value


class AdminFeeScheduleViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Versions are immutable: changing fees means creating a new version (audited)."""

    permission_classes = [IsAdmin]
    serializer_class = FeeScheduleSerializer
    queryset = FeeSchedule.objects.order_by("-fiscal_year", "-version")
    lookup_value_regex = UUID_REGEX
    filter_backends: list = []

    def create(self, request):
        serializer = FeeScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = create_schedule_version(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(FeeScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)
