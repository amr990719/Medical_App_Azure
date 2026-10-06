"""Document endpoints. Doctors reach only documents of their own applications; admins reach
documents of submitted (non-draft) applications. Other ids are 404 — no IDOR."""

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAuthenticatedActive, IsDoctor
from apps.applications.api.views import doctor_applications
from apps.documents.models import Document
from apps.documents.services import delete_document, document_content, store_document
from apps.documents.storage import document_disposition
from apps.reference.constants import ApplicationStatus, DocumentType

from .serializers import DocumentSummarySerializer


def visible_documents(user):
    """Active documents the user may see: own (doctor) or of submitted applications (admin)."""
    if user.role == Role.ADMIN:
        return Document.objects.exclude(application__status=ApplicationStatus.DRAFT)
    return Document.objects.filter(application__doctor__user=user)


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=True, use_url=False)
    document_type = serializers.ChoiceField(choices=DocumentType.choices)
    beneficiary_id = serializers.UUIDField(required=False, allow_null=True)


class DocumentUploadView(APIView):
    """`POST /applications/{id}/documents/` (multipart). Re-uploading a slot replaces it."""

    permission_classes = [IsDoctor]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(
        request={"multipart/form-data": DocumentUploadSerializer},
        responses={201: DocumentSummarySerializer},
        operation_id="documents_upload",
    )
    def post(self, request, application_id):
        application = get_object_or_404(
            doctor_applications(request.user).select_related("doctor"), pk=application_id
        )
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        document = store_document(
            application,
            document_type=data["document_type"],
            upload=data["file"],
            actor=request.user,
            beneficiary_id=data.get("beneficiary_id"),
            request=request,
        )
        return Response(DocumentSummarySerializer(document).data, status=status.HTTP_201_CREATED)


class DeleteOnlyByDoctor(BasePermission):
    def has_permission(self, request, view) -> bool:
        return request.method != "DELETE" or IsDoctor().has_permission(request, view)


class DocumentDetailView(APIView):
    """`GET` metadata (owner or admin) · `DELETE` (owner, only while editable)."""

    permission_classes = [IsAuthenticatedActive, DeleteOnlyByDoctor]

    def get_object(self, pk) -> Document:
        return get_object_or_404(visible_documents(self.request.user), pk=pk)

    @extend_schema(responses=DocumentSummarySerializer, operation_id="documents_retrieve")
    def get(self, request, pk):
        return Response(DocumentSummarySerializer(self.get_object(pk)).data)

    @extend_schema(responses={204: None}, operation_id="documents_destroy")
    def delete(self, request, pk):
        delete_document(self.get_object(pk), actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentContentView(APIView):
    """`GET /documents/{id}/content/` — authorized stream, or a 302 to a ≤5-minute SAS."""

    permission_classes = [IsAuthenticatedActive]

    @extend_schema(
        responses={
            (200, "application/octet-stream"): OpenApiTypes.BINARY,
            302: OpenApiResponse(description="redirect to a read-only SAS URL (≤5 minutes)"),
        },
        operation_id="documents_content",
    )
    def get(self, request, pk):
        document = get_object_or_404(visible_documents(request.user), pk=pk)
        content = document_content(document, actor=request.user, request=request)
        if content.redirect_url:
            response = HttpResponseRedirect(content.redirect_url)
        else:
            response = HttpResponse(content.data, content_type=content.content_type)
            response["Content-Disposition"] = document_disposition(
                content.content_type, content.filename
            )
            response["Content-Length"] = str(len(content.data))
        response["Cache-Control"] = "no-store, private"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response
