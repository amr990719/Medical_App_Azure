from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsDoctor
from apps.doctors.services import get_or_create_doctor, update_profile

from .serializers import DoctorProfileSerializer


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
