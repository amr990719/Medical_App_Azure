"""Doctor application endpoints. Views authenticate, authorize, deserialize, call a service and
serialize — the rules live in `applications.services` / `validation` / `fees.services`.

Every queryset is scoped to the requesting doctor, so another doctor's id is a 404 (no IDOR).
"""

from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsDoctor
from apps.applications import services
from apps.applications.models import InsuranceApplication
from apps.applications.validation import validate_for_submission
from apps.beneficiaries.models import Beneficiary
from apps.common.exceptions import ValidationFailed
from apps.doctors.services import get_or_create_doctor
from apps.documents.models import Document
from apps.fees.services import NoActiveFeeSchedule, quote_for_application

from .serializers import (
    ApplicationCreateSerializer,
    ApplicationSerializer,
    ApplicationUpdateSerializer,
)

UUID_REGEX = r"[0-9a-fA-F-]{36}"


def doctor_applications(user):
    """THE doctor scope: applications owned by `user`. Used by every doctor-facing view."""
    return InsuranceApplication.objects.filter(doctor__user=user)


def with_details(queryset):
    active_documents = Document.objects.order_by("created_at")
    return queryset.select_related("doctor").prefetch_related(
        Prefetch(
            "beneficiaries",
            queryset=Beneficiary.objects.order_by("row_number").prefetch_related(
                Prefetch("documents", queryset=active_documents)
            ),
        ),
        Prefetch("documents", queryset=active_documents),
    )


class ApplicationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsDoctor]
    serializer_class = ApplicationSerializer
    lookup_value_regex = UUID_REGEX
    filter_backends: list = []

    def get_queryset(self):
        return with_details(doctor_applications(self.request.user)).order_by(
            "-fiscal_year", "-created_at"
        )

    def _respond(self, app, status_code=status.HTTP_200_OK):
        app = self.get_queryset().get(pk=app.pk)  # fresh, with nested data
        return Response(ApplicationSerializer(app).data, status=status_code)

    @extend_schema(request=ApplicationCreateSerializer, responses=ApplicationSerializer)
    def create(self, request):
        """Draft for the current fiscal year — 201 when created, 200 with the existing one."""
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app, created = services.get_or_create_draft(
            get_or_create_doctor(request.user),
            actor=request.user,
            application_type=serializer.validated_data["application_type"],
        )
        return self._respond(app, status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=ApplicationUpdateSerializer, responses=ApplicationSerializer)
    def partial_update(self, request, pk=None):
        app = self.get_object()
        serializer = ApplicationUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        app = services.update_draft(app, actor=request.user, changes=serializer.validated_data)
        return self._respond(app)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def fees(self, request, pk=None):
        """Live server quote while editable; the frozen snapshot once submitted."""
        app = self.get_object()
        if not app.is_editable and app.fee_snapshot is not None:
            return Response(app.fee_snapshot)
        try:
            return Response(quote_for_application(app).as_dict())
        except NoActiveFeeSchedule:
            raise ValidationFailed(services.MSG_NO_FEE_SCHEDULE) from None

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def validation(self, request, pk=None):
        """All errors grouped by step (rules 16–17 omitted while drafting) + submit readiness."""
        app = self.get_object()
        result = validate_for_submission(app, stage="form").as_dict()
        result["submit_ready"] = validate_for_submission(app, stage="submit").is_valid
        return Response(result)

    @extend_schema(request=None, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """DRAFT → SUBMITTED or NEEDS_CORRECTION → SUBMITTED (same reference number)."""
        app = services.submit(self.get_object(), actor=request.user, request=request)
        return self._respond(app)
