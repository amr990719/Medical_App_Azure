"""Auth endpoints: `/auth/me/` (user + CSRF bootstrap), `/auth/logout/`, and the development
login (`/auth/dev/users/`, `/auth/dev/login/`), which exists only while DEV_AUTH_ENABLED —
production settings refuse to start with it on."""

from django.conf import settings
from django.http import Http404
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.services import end_session, entra_logout_url, start_session
from config.api.authentication import SessionAuthentication

from .serializers import (
    DevLoginSerializer,
    DevUserSerializer,
    LogoutSerializer,
    MeSerializer,
)

DEV_USERS_LIMIT = 100


def me_payload(request, user) -> dict:
    return MeSerializer({"user": user, "csrf_token": get_token(request)}).data


class MeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=MeSerializer, operation_id="auth_me")
    def get(self, request):
        token = get_token(request)  # sets the csrftoken cookie, also on the 401 response
        if not request.user.is_authenticated:
            raise exceptions.NotAuthenticated()
        return Response(MeSerializer({"user": request.user, "csrf_token": token}).data)


class LogoutView(APIView):
    @extend_schema(request=None, responses=LogoutSerializer, operation_id="auth_logout")
    def post(self, request):
        end_session(request)
        return Response(LogoutSerializer({"entra_logout_url": entra_logout_url()}).data)


class DevAuthMixin:
    def initial(self, request, *args, **kwargs):
        if not settings.DEV_AUTH_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)


class DevUsersView(DevAuthMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=DevUserSerializer(many=True), operation_id="auth_dev_users")
    def get(self, request):
        users = (
            User.objects.filter(is_active=True).select_related("doctor").order_by("role", "email")
        )
        return Response(DevUserSerializer(users[:DEV_USERS_LIMIT], many=True).data)


class DevLoginView(DevAuthMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dev_login"

    @extend_schema(
        request=DevLoginSerializer, responses=MeSerializer, operation_id="auth_dev_login"
    )
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)  # login CSRF protection
        serializer = DevLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["email"]
        start_session(request, user)
        return Response(me_payload(request, user))
