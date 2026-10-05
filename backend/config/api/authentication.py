"""Session authentication for the BFF (PROMPT.md §27).

DRF's SessionAuthentication has no `WWW-Authenticate` challenge, so DRF turns
`NotAuthenticated` into 403. Returning a challenge makes anonymous requests a proper 401
`NOT_AUTHENTICATED`. CSRF is still enforced on unsafe methods for authenticated sessions.
"""

from rest_framework.authentication import SessionAuthentication as DrfSessionAuthentication


class SessionAuthentication(DrfSessionAuthentication):
    def authenticate_header(self, request) -> str:
        return 'Session realm="api"'
