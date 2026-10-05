"""Sign-in / sign-out helpers shared by the development login and the Entra OIDC callback."""

import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login, logout

from .middleware import SESSION_STARTED_KEY

BACKEND = "apps.accounts.backends.SessionOnlyBackend"


def start_session(request, user) -> None:
    """Log the user in with a fresh session id (prevents session fixation)."""
    login(request, user, backend=BACKEND)
    request.session[SESSION_STARTED_KEY] = time.time()


def end_session(request) -> None:
    logout(request)


def entra_logout_url() -> str | None:
    """Entra front-channel sign-out URL, so the hosted session ends too."""
    if not settings.ENTRA_AUTHORITY:
        return None
    query = {}
    if settings.ENTRA_POST_LOGOUT_REDIRECT_URI:
        query["post_logout_redirect_uri"] = settings.ENTRA_POST_LOGOUT_REDIRECT_URI
    url = f"{settings.ENTRA_AUTHORITY.rstrip('/')}/oauth2/v2.0/logout"
    return f"{url}?{urlencode(query)}" if query else url


def display_name(user) -> str:
    doctor = getattr(user, "doctor", None)
    if doctor is not None and doctor.full_name:
        return doctor.full_name
    return user.display_name or user.email
