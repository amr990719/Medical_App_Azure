"""Dues endpoints. Views authenticate, scope the objects, deserialize, call `apps.dues.services`
and serialize. Every queryset is scoped (the member's own applications; admins: submitted ones),
so foreign ids are 404."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin, IsDoctor
from apps.applications.api.admin_serializers import AdminApplicationDetailSerializer
from apps.applications.api.admin_views import admin_detail_response, reviewable_applications
from apps.dues import services
from apps.dues.models import SyndicateDuesRequest

from .serializers import (
    DuesCancelSerializer,
    DuesReceiptUploadSerializer,
    DuesRequestCreateSerializer,
    DuesRequestSerializer,
    DuesReviewSerializer,
)


def _member_dues(user, application_id, dues_id) -> SyndicateDuesRequest:
    return get_object_or_404(
        SyndicateDuesRequest.objects.select_related("application__doctor__user"),
        pk=dues_id,
        application_id=application_id,
        application__doctor__user=user,
    )


def _admin_dues(application_id, dues_id) -> SyndicateDuesRequest:
    return get_object_or_404(
        SyndicateDuesRequest.objects.filter(application__in=reviewable_applications()),
        pk=dues_id,
        application_id=application_id,
    )


class DuesReceiptUploadView(APIView):
    """`POST /applications/{id}/dues-requests/{dues_id}/receipts/` (multipart) — the member's
    receipt for one request. Allowed while the application is under review; no edit needed."""

    permission_classes = [IsDoctor]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(
        request={"multipart/form-data": DuesReceiptUploadSerializer},
        responses={201: DuesRequestSerializer},
        operation_id="dues_receipts_upload",
    )
    def post(self, request, application_id, dues_id):
        dues = _member_dues(request.user, application_id, dues_id)
        serializer = DuesReceiptUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.submit_dues_receipt(
            dues, upload=serializer.validated_data["file"], actor=request.user, request=request
        )
        fresh = _member_dues(request.user, application_id, dues_id)
        return Response(DuesRequestSerializer(fresh).data, status=status.HTTP_201_CREATED)


class AdminDuesRequestCreateView(APIView):
    """`POST /admin/applications/{id}/dues-requests/` {amount, reason}."""

    permission_classes = [IsAdmin]

    @extend_schema(
        request=DuesRequestCreateSerializer,
        responses={201: AdminApplicationDetailSerializer},
        operation_id="admin_dues_requests_create",
    )
    def post(self, request, application_id):
        app = get_object_or_404(reviewable_applications(), pk=application_id)
        serializer = DuesRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.create_dues_request(
            app,
            amount=serializer.validated_data["amount"],
            reason=serializer.validated_data["reason"],
            actor=request.user,
            request=request,
        )
        return admin_detail_response(app, status_code=status.HTTP_201_CREATED)


class AdminDuesReviewView(APIView):
    """`POST /admin/applications/{id}/dues-requests/{dues_id}/review/`
    {receipt_id, decision: CONFIRMED | REJECTED, reason (required to reject)}."""

    permission_classes = [IsAdmin]

    @extend_schema(
        request=DuesReviewSerializer,
        responses=AdminApplicationDetailSerializer,
        operation_id="admin_dues_requests_review",
    )
    def post(self, request, application_id, dues_id):
        dues = _admin_dues(application_id, dues_id)
        serializer = DuesReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.review_dues_receipt(
            dues,
            receipt_id=data.get("receipt_id"),
            decision=data["decision"],
            reason=data["reason"],
            actor=request.user,
            request=request,
        )
        return admin_detail_response(dues.application)


class AdminDuesCancelView(APIView):
    """`POST /admin/applications/{id}/dues-requests/{dues_id}/cancel/` {reason}."""

    permission_classes = [IsAdmin]

    @extend_schema(
        request=DuesCancelSerializer,
        responses=AdminApplicationDetailSerializer,
        operation_id="admin_dues_requests_cancel",
    )
    def post(self, request, application_id, dues_id):
        dues = _admin_dues(application_id, dues_id)
        serializer = DuesCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_dues_request(
            dues, reason=serializer.validated_data["reason"], actor=request.user, request=request
        )
        return admin_detail_response(dues.application)
