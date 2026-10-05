"""Admin endpoints (role ADMIN only). Admins review SUBMITTED-and-later applications; drafts
are the doctor's private work in progress and are not listed. Every status or payment change
goes through `applications.services`."""

from django.conf import settings
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin
from apps.applications import services
from apps.applications.models import InsuranceApplication
from apps.audit.models import AuditLog
from apps.documents.models import Document
from apps.reference.constants import ApplicationStatus, PaymentStatus

from .admin_filters import AdminApplicationFilter
from .admin_serializers import (
    AdminApplicationDetailSerializer,
    AdminApplicationRowSerializer,
    AdminNoteSerializer,
    AdminStatsSerializer,
    AuditEntrySerializer,
    PaymentReviewSerializer,
    TransitionSerializer,
)
from .views import UUID_REGEX, with_details

REVEAL_PARAM = "reveal_national_id"
PENDING_RECEIPT_STATUSES = (
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.NEEDS_CORRECTION,
)


def reviewable_applications():
    return InsuranceApplication.objects.exclude(status=ApplicationStatus.DRAFT)


class AdminStatsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(
        parameters=[OpenApiParameter("fiscal_year", int)],
        responses=AdminStatsSerializer,
        operation_id="admin_stats",
    )
    def get(self, request):
        fiscal_year = int(request.query_params.get("fiscal_year") or settings.CURRENT_FISCAL_YEAR)
        year = InsuranceApplication.objects.filter(fiscal_year=fiscal_year)
        by_status = dict.fromkeys(ApplicationStatus.values, 0)
        by_status.update(dict(year.values_list("status").annotate(n=Count("id"))))
        by_payment = dict.fromkeys(PaymentStatus.values, 0)
        by_payment.update(
            dict(
                year.exclude(status=ApplicationStatus.DRAFT)
                .values_list("payment_status")
                .annotate(n=Count("id"))
            )
        )
        pending = year.filter(
            payment_status=PaymentStatus.PENDING_REVIEW, status__in=PENDING_RECEIPT_STATUSES
        ).count()
        data = {
            "fiscal_year": fiscal_year,
            "total": sum(n for s, n in by_status.items() if s != ApplicationStatus.DRAFT),
            "by_status": by_status,
            "by_payment_status": by_payment,
            "receipts_pending": pending,
        }
        return Response(AdminStatsSerializer(data).data)


class AdminApplicationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAdmin]
    filterset_class = AdminApplicationFilter
    lookup_value_regex = UUID_REGEX

    def get_queryset(self):
        queryset = reviewable_applications().select_related("doctor", "doctor__user", "reviewed_by")
        if self.action == "list":
            return queryset.order_by("-submitted_at", "-created_at")
        return with_details(queryset)

    def get_serializer_class(self):
        return (
            AdminApplicationRowSerializer
            if self.action == "list"
            else AdminApplicationDetailSerializer
        )

    def _detail(self, app, *, reveal=False, status_code=status.HTTP_200_OK):
        fresh = with_details(reviewable_applications().select_related("reviewed_by")).get(pk=app.pk)
        serializer = AdminApplicationDetailSerializer(fresh, context={REVEAL_PARAM: reveal})
        return Response(serializer.data, status=status_code)

    @extend_schema(parameters=[OpenApiParameter(REVEAL_PARAM, bool)])
    def retrieve(self, request, pk=None):
        """Detail with masked national IDs; `reveal_national_id=1` shows them (audited)."""
        app = self.get_object()
        reveal = request.query_params.get(REVEAL_PARAM) in ("1", "true")
        services.record_admin_view(
            app, actor=request.user, revealed_national_id=reveal, request=request
        )
        return self._detail(app, reveal=reveal)

    @extend_schema(request=TransitionSerializer, responses=AdminApplicationDetailSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app = services.transition(
            self.get_object(),
            to_status=serializer.validated_data["to_status"],
            review_notes=serializer.validated_data["review_notes"],
            actor=request.user,
            request=request,
        )
        return self._detail(app)

    @extend_schema(request=PaymentReviewSerializer, responses=AdminApplicationDetailSerializer)
    @action(detail=True, methods=["post"])
    def payment(self, request, pk=None):
        serializer = PaymentReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app = services.review_payment(
            self.get_object(),
            status=serializer.validated_data["payment_status"],
            note=serializer.validated_data["note"],
            actor=request.user,
            request=request,
        )
        return self._detail(app)

    @extend_schema(methods=["GET"], responses=AdminNoteSerializer(many=True))
    @extend_schema(methods=["POST"], request=AdminNoteSerializer, responses=AdminNoteSerializer)
    @action(detail=True, methods=["get", "post"], pagination_class=None)
    def notes(self, request, pk=None):
        """Internal notes — never exposed on any doctor endpoint."""
        app = self.get_object()
        if request.method == "GET":
            notes = app.admin_notes.select_related("author").order_by("created_at")
            return Response(AdminNoteSerializer(notes, many=True).data)
        serializer = AdminNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = services.add_admin_note(
            app, body=serializer.validated_data["body"], actor=request.user, request=request
        )
        return Response(AdminNoteSerializer(note).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=AuditEntrySerializer(many=True))
    @action(detail=True, methods=["get"])
    def audit(self, request, pk=None):
        """Audit history of the application and of its documents (incl. replaced ones)."""
        app = self.get_object()
        document_ids = Document.all_objects.filter(application=app).values("pk")
        entries = (
            AuditLog.objects.filter(Q(object_id=app.pk) | Q(object_id__in=document_ids))
            .select_related("user")
            .order_by("-timestamp")
        )
        page = self.paginate_queryset(entries)
        return self.get_paginated_response(AuditEntrySerializer(page, many=True).data)
