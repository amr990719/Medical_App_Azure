"""The client's address behind the trusted proxies, for throttling and the audit hash.

Production traffic reaches Django through the Static Web Apps linked backend and the Container
Apps ingress; each appends the address it received the request from to X-Forwarded-For. Only
those last `NUM_PROXIES` entries are trustworthy: anything before them was sent by the client.
This is DRF's own rule (`BaseThrottle.get_ident`), shared so the audit log hashes the same
address the throttles count, and with `NUM_PROXIES = 0` the header is ignored entirely.

The chosen entry is reduced to a bare IP (PROXY-1): production's entry carries the client's
source port (`ip:port`), which changes with every new connection, so keying on it gave each
request its own throttle counter. An entry that is not an IP falls back to the peer address.
"""

import ipaddress

from rest_framework.settings import api_settings


def normalize_address(entry: str) -> str | None:
    """`a.b.c.d`, `a.b.c.d:port`, `v6`, `[v6]` or `[v6]:port` -> the bare IP; otherwise None."""
    host = entry.strip()
    if host.startswith("["):
        end = host.find("]")
        rest = host[end + 1 :] if end != -1 else ""
        if end == -1 or (rest and not (rest.startswith(":") and rest[1:].isdigit())):
            return None
        host = host[1:end]
    elif host.count(":") == 1:  # IPv4 with a port; bare IPv6 has two or more colons
        host, port = host.split(":")
        if not port.isdigit():
            return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def client_ip(request) -> str:
    remote = request.META.get("REMOTE_ADDR", "")
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    trusted = api_settings.NUM_PROXIES or 0
    if not forwarded or trusted <= 0:
        return remote
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if not entries:
        return remote
    return normalize_address(entries[-min(trusted, len(entries))]) or remote
