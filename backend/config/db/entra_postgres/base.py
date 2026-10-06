"""PostgreSQL backend authenticating with a Microsoft Entra access token (PROMPT.md §26).

Azure Database for PostgreSQL Flexible Server accepts an Entra access token as the password of
an Entra-mapped role (here: the Container App's managed identity, `USER` = the role name). A
token is fetched for every NEW connection (cached until 5 minutes before it expires), so
persistent connections (`CONN_MAX_AGE`, capped in production settings) never outlive the token
they were opened with by much and reconnects always present a valid one. TLS is mandatory.

Select it with `ENGINE = "config.db.entra_postgres"` (production settings do so when
`DB_AUTH_MODE=entra`). NOT VERIFIED against Azure — requires Azure credentials.
"""

import threading
import time

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.postgresql import base as postgresql

POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
REFRESH_MARGIN_SECONDS = 300
TLS_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})


class _TokenCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.token: str | None = None
        self.expires_on = 0

    def clear(self) -> None:
        with self._lock:
            self.token, self.expires_on = None, 0

    def get(self) -> str:
        with self._lock:
            if self.token is None or self.expires_on - time.time() <= REFRESH_MARGIN_SECONDS:
                from config.azure import get_azure_credential

                access = get_azure_credential().get_token(POSTGRES_SCOPE)
                self.token, self.expires_on = access.token, access.expires_on
            return self.token


token_cache = _TokenCache()


class DatabaseWrapper(postgresql.DatabaseWrapper):
    def get_connection_params(self):
        params = super().get_connection_params()
        if params.get("sslmode") not in TLS_SSLMODES:
            raise ImproperlyConfigured(
                "Entra PostgreSQL authentication requires TLS: set OPTIONS['sslmode'] "
                "(DB_SSLMODE) to require, verify-ca or verify-full."
            )
        params["password"] = token_cache.get()
        return params
