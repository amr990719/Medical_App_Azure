"""Session authentication, CSRF bootstrap and the development login (PROMPT.md §27)."""

from datetime import timedelta

import pytest
from django.contrib.auth import authenticate
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.doctors.factories import DoctorFactory

pytestmark = pytest.mark.django_db

ME = "/api/v1/auth/me/"
LOGOUT = "/api/v1/auth/logout/"
DEV_LOGIN = "/api/v1/auth/dev/login/"
DEV_USERS = "/api/v1/auth/dev/users/"


def csrf_client() -> APIClient:
    """A client that enforces CSRF like a browser would."""
    return APIClient(enforce_csrf_checks=True)


def bootstrap_csrf(client: APIClient) -> str:
    client.get(ME)
    return client.cookies["csrftoken"].value


def dev_login(client: APIClient, email: str):
    token = bootstrap_csrf(client)
    return client.post(DEV_LOGIN, {"email": email}, format="json", HTTP_X_CSRFTOKEN=token)


# --- /auth/me/ ---------------------------------------------------------------------------------


def test_me_anonymous_returns_401_envelope_and_sets_csrf_cookie():
    client = csrf_client()
    response = client.get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert "csrftoken" in response.cookies


def test_dev_login_sets_session_and_me_returns_role():
    user = UserFactory(email="doc@example.test")
    DoctorFactory(user=user, full_name="أحمد محمد علي")
    client = csrf_client()
    response = dev_login(client, "DOC@example.test")
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "doc@example.test"

    me = client.get(ME).json()
    assert me["user"] == {
        "id": str(user.pk),
        "email": "doc@example.test",
        "role": "DOCTOR",
        "display_name": "أحمد محمد علي",
        "has_profile": True,
    }
    assert me["csrf_token"]


def test_session_cookie_is_httponly_and_samesite_lax():
    UserFactory(email="doc@example.test")
    client = csrf_client()
    response = dev_login(client, "doc@example.test")
    cookie = response.cookies["sessionid"]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"


def test_admin_me_reports_admin_role():
    AdminUserFactory(email="boss@example.test")
    client = csrf_client()
    dev_login(client, "boss@example.test")
    assert client.get(ME).json()["user"]["role"] == "ADMIN"


# --- CSRF --------------------------------------------------------------------------------------


def test_dev_login_without_csrf_token_rejected():
    UserFactory(email="doc@example.test")
    client = csrf_client()
    client.get(ME)
    response = client.post(DEV_LOGIN, {"email": "doc@example.test"}, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_unsafe_request_without_csrf_rejected():
    UserFactory(email="doc@example.test")
    client = csrf_client()
    dev_login(client, "doc@example.test")
    response = client.post(LOGOUT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert client.get(ME).status_code == 200  # still signed in


# --- logout ------------------------------------------------------------------------------------


def test_logout_clears_session():
    UserFactory(email="doc@example.test")
    client = csrf_client()
    dev_login(client, "doc@example.test")
    token = client.cookies["csrftoken"].value
    response = client.post(LOGOUT, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert client.get(ME).status_code == 401


def test_logout_returns_entra_logout_url_when_configured():
    UserFactory(email="doc@example.test")
    client = csrf_client()
    dev_login(client, "doc@example.test")
    token = client.cookies["csrftoken"].value
    with override_settings(
        ENTRA_AUTHORITY="https://contoso.ciamlogin.com/tenant-guid",
        ENTRA_POST_LOGOUT_REDIRECT_URI="https://app.example.test/",
    ):
        body = client.post(LOGOUT, HTTP_X_CSRFTOKEN=token).json()
    assert body["entra_logout_url"].startswith(
        "https://contoso.ciamlogin.com/tenant-guid/oauth2/v2.0/logout?"
    )
    assert "post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2F" in body["entra_logout_url"]


# --- dev login availability ------------------------------------------------------------------


@override_settings(DEV_AUTH_ENABLED=False)
def test_dev_login_disabled_returns_404():
    UserFactory(email="doc@example.test")
    client = APIClient()
    assert client.post(DEV_LOGIN, {"email": "doc@example.test"}, format="json").status_code == 404
    assert client.get(DEV_USERS).status_code == 404


def test_dev_users_lists_active_users_without_national_ids():
    DoctorFactory(user=UserFactory(email="doc@example.test"))
    AdminUserFactory(email="boss@example.test")
    UserFactory(email="gone@example.test", is_active=False)
    response = APIClient().get(DEV_USERS)
    assert response.status_code == 200
    emails = {u["email"]: u["role"] for u in response.json()}
    assert emails == {"doc@example.test": "DOCTOR", "boss@example.test": "ADMIN"}
    assert "national_id" not in str(response.json())


def test_dev_login_unknown_email_is_a_validation_error():
    response = dev_login(csrf_client(), "nobody@example.test")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_dev_login_refuses_inactive_user():
    UserFactory(email="gone@example.test", is_active=False)
    assert dev_login(csrf_client(), "gone@example.test").status_code == 400


def _dev_login_create(client: APIClient, email: str):
    token = bootstrap_csrf(client)
    return client.post(
        DEV_LOGIN, {"email": email, "create": True}, format="json", HTTP_X_CSRFTOKEN=token
    )


def test_dev_login_create_makes_a_fresh_doctor_for_end_to_end_runs():
    from apps.accounts.models import User

    client = csrf_client()
    response = _dev_login_create(client, "E2E-1@dev.local")
    assert response.status_code == 200
    user = User.objects.get(email="e2e-1@dev.local")
    assert user.role == "DOCTOR"
    assert not user.has_usable_password()
    assert client.get(ME).json()["user"]["email"] == "e2e-1@dev.local"


def test_dev_login_create_reuses_an_existing_user_and_never_changes_its_role():
    AdminUserFactory(email="boss@example.test")
    response = _dev_login_create(csrf_client(), "boss@example.test")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "ADMIN"


def test_dev_login_create_refuses_inactive_user():
    UserFactory(email="gone@example.test", is_active=False)
    assert _dev_login_create(csrf_client(), "gone@example.test").status_code == 400


def test_dev_login_create_survives_a_concurrent_create(monkeypatch):
    """Two parallel e2e workers signing in with the same new e-mail: the one that loses the
    INSERT race must sign in as the user the other created, not answer 500."""
    from apps.accounts.models import User

    client = csrf_client()
    token = bootstrap_csrf(client)
    UserFactory(email="race@dev.local")  # the concurrent request's INSERT committed first
    real_filter = User.objects.filter
    calls = {"n": 0}

    def stale_first_lookup(*args, **kwargs):
        calls["n"] += 1
        queryset = real_filter(*args, **kwargs)
        return queryset.none() if calls["n"] == 1 else queryset

    monkeypatch.setattr(User.objects, "filter", stale_first_lookup)
    response = client.post(
        DEV_LOGIN, {"email": "race@dev.local", "create": True}, format="json",
        HTTP_X_CSRFTOKEN=token,
    )  # fmt: skip
    assert response.status_code == 200, response.json()
    assert response.json()["user"]["email"] == "race@dev.local"
    assert real_filter(email="race@dev.local").count() == 1


@override_settings(DEV_AUTH_ENABLED=False)
def test_dev_login_create_disabled_returns_404():
    from apps.accounts.models import User

    client = csrf_client()
    response = client.post(DEV_LOGIN, {"email": "x@dev.local", "create": True}, format="json")
    assert response.status_code == 404
    assert not User.objects.filter(email="x@dev.local").exists()


# --- session lifetime and backend -------------------------------------------------------------


def test_deactivated_user_session_is_rejected():
    user = UserFactory(email="doc@example.test")
    client = csrf_client()
    dev_login(client, "doc@example.test")
    user.is_active = False
    user.save()
    assert client.get(ME).status_code == 401


def test_absolute_session_timeout_signs_out(settings):
    UserFactory(email="doc@example.test")
    client = csrf_client()
    dev_login(client, "doc@example.test")
    session = client.session
    session["auth_started_at"] = (
        timezone.now() - timedelta(seconds=settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS + 1)
    ).timestamp()
    session.save()
    assert client.get(ME).status_code == 401


def test_password_authentication_is_impossible():
    user = UserFactory(email="doc@example.test")
    user.set_password("correct horse battery")
    user.save()
    assert authenticate(email="doc@example.test", password="correct horse battery") is None
    assert authenticate(username="doc@example.test", password="correct horse battery") is None
