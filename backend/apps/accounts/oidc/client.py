"""MSAL confidential client for the Entra External ID authorization code flow.

`initiate_auth_code_flow` creates the PKCE verifier/challenge (S256), `state` and `nonce`;
`acquire_token_by_auth_code_flow` checks `state`, sends the verifier and redeems the code.
The flow dict lives only in the server-side session; tokens never reach the browser.
"""

import logging

import msal
from django.conf import settings

from .claims import OidcError

logger = logging.getLogger("apps.accounts.oidc")
RESERVED_SCOPES = {"openid", "profile", "offline_access"}  # MSAL adds these itself


def is_configured() -> bool:
    return bool(
        settings.ENTRA_AUTHORITY
        and settings.ENTRA_CLIENT_ID
        and settings.ENTRA_CLIENT_SECRET
        and settings.ENTRA_REDIRECT_URI
    )


class OidcClient:
    def __init__(self) -> None:
        self._app = msal.ConfidentialClientApplication(
            client_id=settings.ENTRA_CLIENT_ID,
            client_credential=settings.ENTRA_CLIENT_SECRET,
            authority=settings.ENTRA_AUTHORITY,
        )

    def begin(self, *, redirect_uri: str) -> dict:
        scopes = [s for s in settings.ENTRA_SCOPES if s not in RESERVED_SCOPES]
        return self._app.initiate_auth_code_flow(scopes=scopes, redirect_uri=redirect_uri)

    def complete(self, flow: dict, params: dict) -> dict:
        try:
            result = self._app.acquire_token_by_auth_code_flow(flow, params)
        except ValueError:  # state mismatch or malformed flow
            raise OidcError() from None
        if "error" in result or "id_token" not in result:
            logger.warning("Token exchange failed", extra={"error": result.get("error", "")})
            raise OidcError()
        return result


def get_oidc_client() -> OidcClient:
    return OidcClient()
