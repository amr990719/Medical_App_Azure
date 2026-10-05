"""`/applications/{application_id}/beneficiaries/` — nested under the doctor's own application.

The parent application is looked up inside the doctor scope first, then the beneficiary inside
that application, so neither id can reach another doctor's data.
"""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsDoctor
from apps.applications.api.views import UUID_REGEX, doctor_applications
from apps.beneficiaries import services
from apps.beneficiaries.models import Beneficiary
from apps.documents.models import Document

from .serializers import BeneficiarySerializer, BeneficiaryWriteSerializer


class BeneficiaryViewSet(viewsets.GenericViewSet):
    permission_classes = [IsDoctor]
    serializer_class = BeneficiarySerializer
    pagination_class = None  # at most MAX_BENEFICIARIES rows
    filter_backends: list = []
    lookup_value_regex = UUID_REGEX

    def get_application(self):
        return get_object_or_404(
            doctor_applications(self.request.user).select_related("doctor"),
            pk=self.kwargs["application_id"],
        )

    def get_queryset(self):
        return (
            Beneficiary.objects.filter(application=self.get_application())
            .select_related("application__doctor")
            .prefetch_related(
                Prefetch("documents", queryset=Document.objects.order_by("created_at"))
            )
            .order_by("row_number")
        )

    def _respond(self, beneficiary, status_code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=beneficiary.pk)
        return Response(BeneficiarySerializer(fresh).data, status=status_code)

    def list(self, request, application_id=None):
        return Response(BeneficiarySerializer(self.get_queryset(), many=True).data)

    @extend_schema(request=BeneficiaryWriteSerializer, responses=BeneficiarySerializer)
    def create(self, request, application_id=None):
        serializer = BeneficiaryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        beneficiary = services.add_beneficiary(
            self.get_application(), actor=request.user, **serializer.validated_data
        )
        return self._respond(beneficiary, status.HTTP_201_CREATED)

    @extend_schema(request=BeneficiaryWriteSerializer, responses=BeneficiarySerializer)
    def partial_update(self, request, application_id=None, pk=None):
        beneficiary = self.get_object()
        serializer = BeneficiaryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = {k: v for k, v in serializer.validated_data.items() if k != "row_number"}
        beneficiary = services.update_beneficiary(beneficiary, actor=request.user, changes=changes)
        return self._respond(beneficiary)

    def destroy(self, request, application_id=None, pk=None):
        services.delete_beneficiary(self.get_object(), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
