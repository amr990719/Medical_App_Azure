from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsDoctor
from apps.documents.models import Document
from apps.ocr.services import extract_document


class OcrSuggestionSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_type = serializers.CharField()
    fields = serializers.DictField()


class ExtractView(APIView):
    """`POST /documents/{id}/extract/` — OCR suggestions for the doctor's own document.
    Rate limited per user (OCR_RATE_LIMIT, default 30/hour). Nothing is saved."""

    permission_classes = [IsDoctor]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ocr"

    @extend_schema(
        request=None, responses=OcrSuggestionSerializer, operation_id="documents_extract"
    )
    def post(self, request, pk):
        document = get_object_or_404(
            Document.objects.filter(application__doctor__user=request.user).select_related(
                "application__doctor"
            ),
            pk=pk,
        )
        suggestion = extract_document(document, actor=request.user, request=request)
        return Response(
            OcrSuggestionSerializer(
                {
                    "document_id": suggestion.document_id,
                    "document_type": suggestion.document_type,
                    "fields": suggestion.fields,
                }
            ).data
        )
