import hashlib
import hmac

from django.conf import settings

from apps.common.client_ip import client_ip

from .models import AuditLog

# Never stored in audit metadata: record IDs and changed field NAMES instead (PROMPT.md §39).
SENSITIVE_KEYS = frozenset(
    {
        "national_id",
        "review_notes_text",
        "password",
        "token",
        "access_token",
        "id_token",
        "refresh_token",
        "secret",
        "cookie",
    }
)


def _scrub(value):
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _ip_hash(request) -> str:
    if request is None:
        return ""
    ip = client_ip(request)  # the address the throttles count, never a client-sent entry
    if not ip:
        return ""
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()


def record(*, actor, action: str, obj, metadata: dict | None = None, request=None) -> AuditLog:
    """Append one audit entry. `actor=None` marks a system action."""
    return AuditLog.objects.create(
        user=actor,
        action=action,
        object_type=obj._meta.object_name,
        object_id=obj.pk,
        ip_hash=_ip_hash(request),
        metadata=_scrub(metadata or {}),
    )
