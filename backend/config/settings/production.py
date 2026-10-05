"""Production settings (Azure Container Apps behind Static Web Apps; PROMPT.md §30).

Import fails with ImproperlyConfigured when a required setting is missing or unsafe, so a
misconfigured revision never starts serving traffic.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import DATABASES, env

MIN_SECRET_KEY_LENGTH = 50


def _require(name: str) -> str:
    value = env(name, default="")
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


if env.bool("DEBUG", default=False):
    raise ImproperlyConfigured("DEBUG must be false in production.")
if env.bool("DEV_AUTH_ENABLED", default=False):
    raise ImproperlyConfigured("DEV_AUTH_ENABLED must never be enabled in production.")

DEBUG = False
DEV_AUTH_ENABLED = False

SECRET_KEY = _require("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
    raise ImproperlyConfigured(
        f"DJANGO_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters."
    )

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not contain '*' in production.")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

_require("DATABASE_URL")
DATABASES["default"]["OPTIONS"]["sslmode"] = env("DB_SSLMODE", default="require")

# --- HTTPS and cookies (TLS terminates at the Container Apps / SWA edge) -----------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^api/health/$", r"^api/ready/$"]  # platform probes use plain HTTP
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # opt in deliberately once the domain is final
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

# Request bodies: documents are streamed as multipart; non-file payloads stay small.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
