from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsDoctor
from apps.doctors.services import get_or_create_doctor, set_whatsapp_opt_in, update_profile

from .serializers import (
    DoctorProfileSerializer,
    NotificationPreferenceInputSerializer,
    NotificationPreferenceSerializer,
)


class ProfileView(APIView):
    """`GET/PATCH /api/v1/profile/` — always the requesting doctor's own profile."""

    permission_classes = [IsDoctor]

    @extend_schema(responses=DoctorProfileSerializer, operation_id="profile_retrieve")
    def get(self, request):
        return Response(DoctorProfileSerializer(get_or_create_doctor(request.user)).data)

    @extend_schema(
        request=DoctorProfileSerializer,
        responses=DoctorProfileSerializer,
        operation_id="profile_partial_update",
    )
    def patch(self, request):
        doctor = get_or_create_doctor(request.user)
        serializer = DoctorProfileSerializer(doctor, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        doctor = update_profile(doctor, actor=request.user, changes=serializer.validated_data)
        return Response(DoctorProfileSerializer(doctor).data)


class NotificationPreferenceView(APIView):
    """`GET/PUT /api/v1/profile/notifications/` — the doctor's own WhatsApp consent."""

    permission_classes = [IsDoctor]

    @extend_schema(
        responses=NotificationPreferenceSerializer, operation_id="profile_notifications_retrieve"
    )
    def get(self, request):
        doctor = get_or_create_doctor(request.user)
        return Response(NotificationPreferenceSerializer(doctor).data)

    @extend_schema(
        request=NotificationPreferenceInputSerializer,
        responses=NotificationPreferenceSerializer,
        operation_id="profile_notifications_update",
    )
    def put(self, request):
        serializer = NotificationPreferenceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = set_whatsapp_opt_in(
            get_or_create_doctor(request.user),
            enabled=serializer.validated_data["whatsapp_opt_in"],
            actor=request.user,
            request=request,
        )
        return Response(NotificationPreferenceSerializer(doctor).data)
