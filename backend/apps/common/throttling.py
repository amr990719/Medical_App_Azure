"""DRF throttles keyed on the normalised client address (PROXY-1).

DRF's own `get_ident` returns the X-Forwarded-For entry verbatim, port included. Every view
uses `ScopedRateThrottle` from here so anonymous counters key on `client_ip()`, the same
address the audit log hashes. Authenticated requests still key on the user id.
"""

from rest_framework import throttling

from apps.common.client_ip import client_ip


class ClientAddressThrottleMixin:
    def get_ident(self, request) -> str:
        return client_ip(request)


class ScopedRateThrottle(ClientAddressThrottleMixin, throttling.ScopedRateThrottle):
    pass
