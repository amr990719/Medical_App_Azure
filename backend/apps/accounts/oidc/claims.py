"""ID-token validation and user mapping for Entra External ID (PROMPT.md §27).

MSAL runs the code flow (PKCE, state, nonce) but does not verify the ID-token signature, so the
token is validated here independently: RS256 signature against the tenant's JWKS, issuer,
audience, expiry/not-before, nonce, and tenant. Users are matched by (oid, tid) only — an email
match alone never links an identity to an existing account.
"""

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
import requests
from django.conf import settings
from django.db import IntegrityError, transaction

from apps.accounts.models import User

logger = logging.getLogger("apps.accounts.oidc")
DISCOVERY_TIMEOUT_SECONDS = 10


class OidcError(Exception):
    """Sign-in refused. `code` is safe to show; details are never echoed to the browser."""

    def __init__(self, code: str = "AUTH_FAILED") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class EntraIdentity:
    oid: str
    tid: str
    email: str
    name: str
    amr: tuple[str, ...]


@lru_cache(maxsize=4)
def _discovery(authority: str) -> dict:
    url = f"{authority.rstrip('/')}/v2.0/.well-known/openid-configuration"
    response = requests.get(url, timeout=DISCOVERY_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=4)
def _jwks_client(uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(uri, cache_keys=True, lifespan=3600)


def expected_issuer() -> str:
    return settings.ENTRA_ISSUER or _discovery(settings.ENTRA_AUTHORITY)["issuer"]


def jwks_uri() -> str:
    return settings.ENTRA_JWKS_URI or _discovery(settings.ENTRA_AUTHORITY)["jwks_uri"]


def signing_key(raw_token: str):
    """Public key for the token's `kid` from the tenant JWKS (cached)."""
    return _jwks_client(jwks_uri()).get_signing_key_from_jwt(raw_token).key


def nonce_claim(flow_nonce: str) -> str:
    """MSAL keeps the raw nonce in the flow and sends its SHA-256 hex digest to the authority
    (msal.oauth2cli.oidc), so the digest is what a genuine ID token carries."""
    return hashlib.sha256(flow_nonce.encode("ascii")).hexdigest()


def validate_id_token(raw_token: str, *, nonce: str) -> dict:
    """`nonce` is the raw nonce from the session flow."""
    try:
        claims = jwt.decode(
            raw_token,
            signing_key(raw_token),
            algorithms=["RS256"],
            audience=settings.ENTRA_CLIENT_ID,
            issuer=expected_issuer(),
            leeway=settings.ENTRA_CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except (jwt.PyJWTError, requests.RequestException) as exc:
        logger.warning("ID token rejected", extra={"reason": type(exc).__name__})
        raise OidcError() from None
    if not nonce or claims.get("nonce") != nonce_claim(nonce):
        logger.warning("ID token rejected", extra={"reason": "nonce"})
        raise OidcError()
    tenant = settings.ENTRA_TENANT_ID
    if tenant and claims.get("tid") != tenant:
        logger.warning("ID token rejected", extra={"reason": "tenant"})
        raise OidcError()
    return claims


def identity_from_claims(claims: dict) -> EntraIdentity:
    oid, tid = claims.get("oid"), claims.get("tid")
    emails = claims.get("emails") or []
    email = claims.get("email") or (emails[0] if emails else "")
    if not oid or not tid:
        raise OidcError()
    if not email:
        raise OidcError("EMAIL_CLAIM_MISSING")
    return EntraIdentity(
        oid=str(oid),
        tid=str(tid),
        email=str(email).strip().lower(),
        name=str(claims.get("name") or "")[:200],
        amr=tuple(str(a) for a in claims.get("amr") or []),
    )


def get_or_create_user(identity: EntraIdentity) -> User:
    """Find the user by (oid, tid); create one on first sign-in. Email and name are refreshed
    from the verified token, but an email already used by another account is never taken over."""
    email_taken = (
        User.objects.filter(email=identity.email)
        .exclude(entra_oid=identity.oid, entra_tid=identity.tid)
        .exists()
    )
    try:
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(entra_oid=identity.oid, entra_tid=identity.tid)
                .first()
            )
            if user is None:
                if email_taken:
                    raise OidcError("EMAIL_IN_USE")
                return User.objects.create_user(
                    identity.email,
                    entra_oid=identity.oid,
                    entra_tid=identity.tid,
                    display_name=identity.name,
                )
            update_fields = []
            if identity.name and user.display_name != identity.name:
                user.display_name = identity.name
                update_fields.append("display_name")
            if user.email != identity.email and not email_taken:
                user.email = identity.email
                update_fields.append("email")
            if update_fields:
                user.save(update_fields=update_fields)
            return user
    except IntegrityError:  # concurrent first sign-in or email race: the constraint decides
        raise OidcError("EMAIL_IN_USE") from None
