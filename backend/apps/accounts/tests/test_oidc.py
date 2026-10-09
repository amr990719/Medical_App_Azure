"""Entra External ID OIDC BFF (PROMPT.md §27): authorization code + PKCE via MSAL, independent
ID-token validation, user mapped by (oid, tid), Django session, safe redirects.

MSAL is replaced at the `OidcClient` boundary; ID tokens are real RS256 JWTs signed with a key
generated per test run, so signature, issuer, audience, nonce and expiry checks really run.
The fake follows MSAL's nonce contract: the flow keeps the raw nonce, the authority receives (and
the ID token carries) its SHA-256 hex digest."""

import hashlib
import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.models import Role, User
from apps.accounts.oidc import claims as claims_module
from apps.accounts.oidc.claims import OidcError, validate_id_token

pytestmark = pytest.mark.django_db

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ISSUER = f"https://{TENANT}.ciamlogin.com/{TENANT}/v2.0"
ENTRA = {
    "ENTRA_AUTHORITY": f"https://contoso.ciamlogin.com/{TENANT}",
    "ENTRA_TENANT_ID": TENANT,
    "ENTRA_CLIENT_ID": CLIENT_ID,
    "ENTRA_CLIENT_SECRET": "test-secret-not-real",
    "ENTRA_REDIRECT_URI": "https://app.example.test/api/v1/auth/callback/",
    "ENTRA_ISSUER": ISSUER,
    "ENTRA_JWKS_URI": "https://example.test/keys",
}
LOGIN = "/api/v1/auth/login/"
CALLBACK = "/api/v1/auth/callback/"
FLOW_NONCE = "nonce-1"  # kept in the session flow
NONCE_CLAIM = hashlib.sha256(FLOW_NONCE.encode("ascii")).hexdigest()  # sent to, echoed by Entra

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def entra_settings(settings):
    for key, value in ENTRA.items():
        setattr(settings, key, value)
    with mock.patch.object(
        claims_module, "signing_key", return_value=PRIVATE_KEY.public_key()
    ) as patched:
        yield patched


def make_token(*, key=PRIVATE_KEY, nonce=NONCE_CLAIM, **overrides) -> str:
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "subject-1",
        "oid": "oid-1",
        "tid": TENANT,
        "email": "doctor@example.test",
        "name": "د. أحمد",
        "nonce": nonce,
        "iat": now,
        "nbf": now,
        "exp": now + 600,
    }
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "k1"})


class FakeOidcClient:
    """Stands in for the MSAL-backed client: same interface, no network."""

    def __init__(self, token: str | None = None, error: str | None = None):
        self.token = token
        self.error = error
        self.completed_with = None

    def begin(self, *, redirect_uri: str) -> dict:
        return {
            "auth_uri": f"{ENTRA['ENTRA_AUTHORITY']}/oauth2/v2.0/authorize?client_id={CLIENT_ID}"
            f"&code_challenge=abc&code_challenge_method=S256&state=state-1&nonce={NONCE_CLAIM}",
            "state": "state-1",
            "nonce": FLOW_NONCE,
            "code_verifier": "verifier-secret",
            "redirect_uri": redirect_uri,
        }

    def complete(self, flow: dict, params: dict) -> dict:
        self.completed_with = (flow, params)
        if self.error:
            raise OidcError("AUTH_FAILED")
        return {"id_token": self.token, "id_token_claims": jwt.decode(
            self.token, options={"verify_signature": False})}  # fmt: skip


def sign_in(client: APIClient, fake: FakeOidcClient, *, next_url: str = "/dashboard"):
    with mock.patch("apps.accounts.oidc.views.get_oidc_client", return_value=fake):
        client.get(LOGIN, {"next": next_url})
        return client.get(CALLBACK, {"code": "auth-code", "state": "state-1"})


def redirect_query(response) -> dict:
    return parse_qs(urlparse(response["Location"]).query)


# --- login -------------------------------------------------------------------------------------


def test_login_redirects_to_authority_and_stores_flow():
    client = APIClient()
    with mock.patch("apps.accounts.oidc.views.get_oidc_client", return_value=FakeOidcClient()):
        response = client.get(LOGIN, {"next": "/dashboard"})
    assert response.status_code == 302
    assert response["Location"].startswith(f"{ENTRA['ENTRA_AUTHORITY']}/oauth2/v2.0/authorize")
    assert "code_challenge_method=S256" in response["Location"]  # PKCE
    flow = client.session["oidc_flow"]
    assert flow["state"] == "state-1"
    assert flow["redirect_uri"] == ENTRA["ENTRA_REDIRECT_URI"]
    assert client.session["oidc_next"] == "/dashboard"


@pytest.mark.parametrize(
    "unsafe", ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:x", ""]
)
def test_login_replaces_unsafe_next_with_root(unsafe):
    client = APIClient()
    with mock.patch("apps.accounts.oidc.views.get_oidc_client", return_value=FakeOidcClient()):
        client.get(LOGIN, {"next": unsafe})
    assert client.session["oidc_next"] == "/"


@override_settings(ENTRA_AUTHORITY="", ENTRA_CLIENT_ID="")
def test_login_when_entra_not_configured_returns_503_envelope():
    response = APIClient().get(LOGIN)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_UNAVAILABLE"


# --- callback ----------------------------------------------------------------------------------


def test_callback_creates_user_by_oid_tid_and_starts_session():
    client = APIClient()
    fake = FakeOidcClient(make_token())
    response = sign_in(client, fake)
    assert response.status_code == 302
    assert response["Location"] == "/dashboard"
    user = User.objects.get(entra_oid="oid-1", entra_tid=TENANT)
    assert user.email == "doctor@example.test"
    assert user.display_name == "د. أحمد"
    assert user.role == Role.DOCTOR
    assert not user.has_usable_password()
    assert client.get("/api/v1/auth/me/").json()["user"]["id"] == str(user.pk)
    assert "oidc_flow" not in client.session
    flow, params = fake.completed_with
    assert flow["code_verifier"] == "verifier-secret"
    assert params["code"] == "auth-code"


def test_callback_existing_user_matched_by_oid_and_profile_refreshed():
    user = UserFactory(email="old@example.test", entra_oid="oid-1", entra_tid=TENANT)
    sign_in(APIClient(), FakeOidcClient(make_token(email="new@example.test", name="اسم جديد")))
    user.refresh_from_db()
    assert user.email == "new@example.test"
    assert user.display_name == "اسم جديد"
    assert User.objects.count() == 1


def test_callback_same_email_different_oid_is_never_linked():
    victim = UserFactory(email="doctor@example.test", entra_oid="victim-oid", entra_tid=TENANT)
    client = APIClient()
    response = sign_in(client, FakeOidcClient(make_token(oid="attacker-oid")))
    assert response.status_code == 302
    assert redirect_query(response)["auth_error"] == ["EMAIL_IN_USE"]
    assert client.get("/api/v1/auth/me/").status_code == 401
    victim.refresh_from_db()
    assert victim.entra_oid == "victim-oid"


def test_callback_same_oid_in_other_tenant_is_a_different_identity():
    UserFactory(email="a@example.test", entra_oid="oid-1", entra_tid="other-tenant")
    with override_settings(ENTRA_TENANT_ID=""):
        sign_in(APIClient(), FakeOidcClient(make_token(email="b@example.test")))
    assert User.objects.filter(entra_oid="oid-1").count() == 2


def test_admin_without_mfa_refused():
    AdminUserFactory(email="boss@example.test", entra_oid="oid-1", entra_tid=TENANT)
    client = APIClient()
    response = sign_in(client, FakeOidcClient(make_token(email="boss@example.test", amr=["pwd"])))
    assert redirect_query(response)["auth_error"] == ["MFA_REQUIRED"]
    assert client.get("/api/v1/auth/me/").status_code == 401


def test_mfa_refusal_logs_methods_and_claim_names_only(caplog):
    """Diagnosable without leaking identity: method claims and claim *names*, never values."""
    AdminUserFactory(email="boss@example.test", entra_oid="oid-1", entra_tid=TENANT)
    token = make_token(email="boss@example.test", amr=["pwd"], acr="b2c_1a_x")
    with caplog.at_level("WARNING", logger="apps.accounts.oidc"):
        sign_in(APIClient(), FakeOidcClient(token))
    [record] = [r for r in caplog.records if getattr(r, "reason", None) == "mfa"]
    assert record.amr == ["pwd"]
    assert record.acr == "b2c_1a_x"
    assert {"oid", "tid", "email", "nonce", "amr"} <= set(record.claim_names)
    logged = str(record.__dict__)
    assert "boss@example.test" not in logged and "oid-1" not in logged and TENANT not in logged


def test_admin_with_mfa_accepted():
    AdminUserFactory(email="boss@example.test", entra_oid="oid-1", entra_tid=TENANT)
    client = APIClient()
    token = make_token(email="boss@example.test", amr=["pwd", "mfa"])
    assert sign_in(client, FakeOidcClient(token))["Location"] == "/dashboard"
    assert client.get("/api/v1/auth/me/").json()["user"]["role"] == "ADMIN"


@override_settings(ENTRA_ADMIN_REQUIRE_MFA=False)
def test_admin_mfa_requirement_is_configurable():
    AdminUserFactory(email="boss@example.test", entra_oid="oid-1", entra_tid=TENANT)
    response = sign_in(APIClient(), FakeOidcClient(make_token(email="boss@example.test")))
    assert response["Location"] == "/dashboard"


def test_inactive_user_refused():
    UserFactory(email="doctor@example.test", entra_oid="oid-1", entra_tid=TENANT, is_active=False)
    response = sign_in(APIClient(), FakeOidcClient(make_token()))
    assert redirect_query(response)["auth_error"] == ["ACCOUNT_DISABLED"]


def test_callback_error_from_entra_redirects_with_code_and_no_session():
    client = APIClient()
    with mock.patch(
        "apps.accounts.oidc.views.get_oidc_client", return_value=FakeOidcClient(make_token())
    ):
        client.get(LOGIN)
        response = client.get(
            CALLBACK, {"error": "access_denied", "error_description": "user cancelled"}
        )
    assert response.status_code == 302
    assert redirect_query(response)["auth_error"] == ["AUTH_FAILED"]
    assert client.get("/api/v1/auth/me/").status_code == 401


def test_callback_without_login_flow_is_refused():
    with mock.patch("apps.accounts.oidc.views.get_oidc_client", return_value=FakeOidcClient()):
        response = APIClient().get(CALLBACK, {"code": "x", "state": "y"})
    assert redirect_query(response)["auth_error"] == ["AUTH_FAILED"]


def test_callback_token_exchange_failure_is_refused():
    response = sign_in(APIClient(), FakeOidcClient(make_token(), error="invalid_grant"))
    assert redirect_query(response)["auth_error"] == ["AUTH_FAILED"]


def test_callback_rejects_open_redirect_stored_in_session():
    client = APIClient()
    with mock.patch(
        "apps.accounts.oidc.views.get_oidc_client", return_value=FakeOidcClient(make_token())
    ):
        client.get(LOGIN)
        session = client.session
        session["oidc_next"] = "https://evil.example/steal"
        session.save()
        response = client.get(CALLBACK, {"code": "auth-code", "state": "state-1"})
    assert response["Location"] == "/"


def test_callback_is_rate_limited():
    from rest_framework.throttling import ScopedRateThrottle

    with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth_callback": "2/min"}):
        client = APIClient()
        statuses = [client.get(CALLBACK).status_code for _ in range(3)]
    assert statuses == [302, 302, 429]


# --- ID token validation (signature, issuer, audience, nonce, expiry) ------------------------


def test_valid_token_returns_claims():
    assert validate_id_token(make_token(), nonce=FLOW_NONCE)["oid"] == "oid-1"


@pytest.mark.parametrize(
    "token_kwargs",
    [
        {"key": OTHER_KEY},  # bad signature
        {"iss": "https://evil.example/v2.0"},
        {"aud": "another-client"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"nonce": "replayed"},
        {"nonce": None},
        {"nonce": FLOW_NONCE},  # the raw nonce never leaves the server
    ],
    ids=["signature", "issuer", "audience", "expired", "nonce", "nonce-missing", "nonce-raw"],
)
def test_invalid_tokens_rejected(token_kwargs):
    with pytest.raises(OidcError):
        validate_id_token(make_token(**token_kwargs), nonce=FLOW_NONCE)


def test_nonce_matches_what_msal_sends_to_the_authority():
    """Contract with MSAL itself (no network): the nonce in the authorization request, which the
    ID token echoes, is a digest of the one stored in the flow."""
    from msal.oauth2cli.oidc import Client

    msal_client = Client(
        {"authorization_endpoint": "https://example.test/authorize", "token_endpoint": "x"},
        CLIENT_ID,
    )
    flow = msal_client.initiate_auth_code_flow(redirect_uri=ENTRA["ENTRA_REDIRECT_URI"])
    sent = parse_qs(urlparse(flow["auth_uri"]).query)["nonce"][0]
    assert sent != flow["nonce"]
    assert validate_id_token(make_token(nonce=sent), nonce=flow["nonce"])["oid"] == "oid-1"


def test_unsigned_token_rejected():
    unsigned = jwt.encode({"iss": ISSUER, "aud": CLIENT_ID}, None, algorithm="none")
    with pytest.raises(OidcError):
        validate_id_token(unsigned, nonce=FLOW_NONCE)


def test_token_from_another_tenant_rejected():
    with pytest.raises(OidcError):
        validate_id_token(make_token(tid="another-tenant"), nonce=FLOW_NONCE)


def test_token_without_oid_rejected():
    from apps.accounts.oidc.claims import identity_from_claims

    claims = validate_id_token(make_token(oid=None), nonce=FLOW_NONCE)
    with pytest.raises(OidcError):
        identity_from_claims(claims)
