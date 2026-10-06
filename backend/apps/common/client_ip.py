"""The client's address behind the trusted proxies, for throttling and the audit hash.

Production traffic reaches Django through the Static Web Apps linked backend and the Container
Apps ingress; each appends the address it received the request from to X-Forwarded-For. Only
those last `NUM_PROXIES` entries are trustworthy: anything before them was sent by the client.
This is DRF's own rule (`BaseThrottle.get_ident`), shared so the audit log hashes the same
address the throttles count, and with `NUM_PROXIES = 0` the header is ignored entirely.
"""

from rest_framework.settings import api_settings


def client_ip(request) -> str:
    remote = request.META.get("REMOTE_ADDR", "")
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    trusted = api_settings.NUM_PROXIES or 0
    if not forwarded or trusted <= 0:
        return remote
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if not entries:
        return remote
    return entries[-min(trusted, len(entries))]
