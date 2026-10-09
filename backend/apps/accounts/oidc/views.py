"""`GET /auth/login/` → Entra; `GET /auth/callback/` → validate → session → SPA redirect.

Callback failures redirect to the SPA with `?auth_error=<CODE>` (the browser is navigating, so
a JSON body would strand the user); no detail from Entra is echoed.
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.services import start_session
from apps.common.exceptions import DomainError

from .claims import OidcError, get_or_create_user, identity_from_claims, validate_id_token
from .client import get_oidc_client, is_configured

logger = logging.getLogger("apps.accounts.oidc")

FLOW_KEY = "oidc_flow"
NEXT_KEY = "oidc_next"


class AuthUnavailable(DomainError):
    code = "AUTH_UNAVAILABLE"
    default_message = "تسجيل الدخول غير متاح حالياً"
    status_code = 503


def safe_next(value: str | None) -> str:
    """Only same-site relative paths: rejects absolute URLs, `//host`, backslashes, schemes."""
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or not url_has_allowed_host_and_scheme(value, allowed_hosts=None)
    ):
        return "/"
    return value


def error_redirect(code: str) -> HttpResponseRedirect:
    return HttpResponseRedirect("/?" + urlencode({"auth_error": code}))


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        parameters=[OpenApiParameter("next", str, description="relative SPA path")],
        responses={302: OpenApiResponse(description="redirect to Entra External ID")},
        operation_id="auth_login",
    )
    def get(self, request):
        if not is_configured():
            raise AuthUnavailable()
        flow = get_oidc_client().begin(redirect_uri=settings.ENTRA_REDIRECT_URI)
        request.session[FLOW_KEY] = flow
        request.session[NEXT_KEY] = safe_next(request.query_params.get("next"))
        return HttpResponseRedirect(flow["auth_uri"])


class CallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_callback"

    @extend_schema(
        responses={302: OpenApiResponse(description="session created, redirect to the SPA")},
        operation_id="auth_callback",
    )
    def get(self, request):
        flow = request.session.pop(FLOW_KEY, None)
        next_url = safe_next(request.session.pop(NEXT_KEY, None))
        params = request.query_params.dict()
        try:
            if flow is None or "error" in params or "code" not in params:
                raise OidcError()
            result = get_oidc_client().complete(flow, params)
            claims = validate_id_token(result["id_token"], nonce=flow.get("nonce", ""))
            user = get_or_create_user(identity_from_claims(claims))
            if not user.is_active:
                raise OidcError("ACCOUNT_DISABLED")
            mfa_required = user.role == Role.ADMIN and settings.ENTRA_ADMIN_REQUIRE_MFA
            if mfa_required and "mfa" not in (claims.get("amr") or []):
                # Method claims and claim names only: no identifier, email or token value.
                logger.warning(
                    "Admin sign-in refused",
                    extra={
                        "reason": "mfa",
                        "amr": claims.get("amr"),
                        "acr": claims.get("acr"),
                        "acrs": claims.get("acrs"),
                        "claim_names": sorted(claims),
                    },
                )
                raise OidcError("MFA_REQUIRED")
        except OidcError as error:
            return error_redirect(error.code)
        start_session(request, user)
        return HttpResponseRedirect(next_url)
