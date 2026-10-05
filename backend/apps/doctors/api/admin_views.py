from django.db.models import Count
from rest_framework import mixins, serializers, viewsets

from apps.accounts.permissions import IsAdmin
from apps.applications.api.admin_filters import AdminDoctorFilter
from apps.applications.api.admin_serializers import (
    AdminApplicationRowSerializer,
    AdminDoctorSerializer,
)
from apps.applications.api.views import UUID_REGEX
from apps.doctors.models import Doctor


class AdminDoctorRowSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    masked_national_id = serializers.CharField(read_only=True)
    applications_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            "id", "full_name", "email", "masked_national_id", "syndicate_type", "sub_syndicate",
            "syndicate_registration_number", "governorate", "phone_number", "applications_count",
        ]  # fmt: skip
        read_only_fields = fields


class AdminDoctorDetailSerializer(AdminDoctorSerializer):
    applications = AdminApplicationRowSerializer(many=True, read_only=True)

    class Meta(AdminDoctorSerializer.Meta):
        fields = [*AdminDoctorSerializer.Meta.fields, "applications"]
        read_only_fields = fields


class AdminDoctorViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Members (masked national IDs). Full IDs are revealed only on an application detail."""

    permission_classes = [IsAdmin]
    filterset_class = AdminDoctorFilter
    lookup_value_regex = UUID_REGEX

    def get_queryset(self):
        queryset = Doctor.objects.select_related("user")
        if self.action == "list":
            return queryset.annotate(applications_count=Count("applications")).order_by("full_name")
        return queryset.prefetch_related("applications__doctor")

    def get_serializer_class(self):
        return AdminDoctorRowSerializer if self.action == "list" else AdminDoctorDetailSerializer
