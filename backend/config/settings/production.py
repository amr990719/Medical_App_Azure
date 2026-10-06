"""Production settings (Azure Container Apps behind Static Web Apps; PROMPT.md §26, §29, §30).

Import fails with ImproperlyConfigured when a required setting is missing or unsafe, so a
misconfigured revision never starts serving traffic (the startup check of §30). Secrets come
from the environment (Container Apps Key Vault references) or, for names missing there, from
`KEY_VAULT_URL` read with the managed identity (`config.secrets`).
"""

from django.core.exceptions import ImproperlyConfigured

from config.secrets import load_secrets

from .base import *  # noqa: F403
from .base import DATABASES, LOGGING, MIDDLEWARE, REST_FRAMEWORK, env

MIN_SECRET_KEY_LENGTH = 50
ENTRA_TOKEN_MAX_CONN_AGE = 1800  # seconds; below the lifetime of an Entra access token


def _require(name: str) -> str:
    value = env(name, default="")
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


# --- Startup refusals ----------------------------------------------------------------------- ---
if env.bool("DEBUG", default=False):
    raise ImproperlyConfigured("DEBUG must be false in production.")
if env.bool("DEV_AUTH_ENABLED", default=False):
    raise ImproperlyConfigured("DEV_AUTH_ENABLED must never be enabled in production.")

DEBUG = False
DEV_AUTH_ENABLED = False

# --- Secrets (environment first, then Key Vault) -----------------------------------------------
KEY_VAULT_URL: str = env("KEY_VAULT_URL", default="")
DB_AUTH_MODE: str = env("DB_AUTH_MODE", default="entra")
# DATABASE_PASSWORD only exists in password mode: in Entra mode no Key Vault read may stand
# between a replica and its start (main.bicep injects the other two as Key Vault references).
_secrets = load_secrets(
    ["DJANGO_SECRET_KEY", "ENTRA_CLIENT_SECRET"]
    + (["DATABASE_PASSWORD"] if DB_AUTH_MODE == "password" else []),
    vault_url=KEY_VAULT_URL,
    required=["DJANGO_SECRET_KEY", "ENTRA_CLIENT_SECRET"],
)

SECRET_KEY = _secrets["DJANGO_SECRET_KEY"]
if len(SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
    raise ImproperlyConfigured(
        f"DJANGO_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters."
    )

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not contain '*' in production.")
# The browser's Origin is the Static Web Apps host, not the Container App's.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS must be set in production.")

# --- Microsoft Entra External ID (OIDC BFF, §27) ------------------------------------------------
ENTRA_AUTHORITY = _require("ENTRA_AUTHORITY")
ENTRA_CLIENT_ID = _require("ENTRA_CLIENT_ID")
ENTRA_REDIRECT_URI = _require("ENTRA_REDIRECT_URI")
ENTRA_CLIENT_SECRET = _secrets["ENTRA_CLIENT_SECRET"]

# --- Database (§26): Entra token per new connection, password fallback -------------------------
_require("DATABASE_URL")
_db = DATABASES["default"]
_db["OPTIONS"]["sslmode"] = env("DB_SSLMODE", default="require")
if _db["OPTIONS"]["sslmode"] not in {"require", "verify-ca", "verify-full"}:
    raise ImproperlyConfigured("DB_SSLMODE must be require, verify-ca or verify-full.")
if DB_AUTH_MODE == "entra":
    # USER is the managed identity's PostgreSQL role; the password is a fresh access token.
    _db["ENGINE"] = "config.db.entra_postgres"
    _db["PASSWORD"] = ""
    _db["CONN_MAX_AGE"] = min(_db["CONN_MAX_AGE"], ENTRA_TOKEN_MAX_CONN_AGE)
elif DB_AUTH_MODE == "password":
    _db["PASSWORD"] = _secrets.get("DATABASE_PASSWORD") or _db.get("PASSWORD", "")
    if not _db["PASSWORD"]:
        raise ImproperlyConfigured(
            "DB_AUTH_MODE=password needs DATABASE_PASSWORD (Key Vault secret "
            "'database-password') or a password in DATABASE_URL."
        )
else:
    raise ImproperlyConfigured("DB_AUTH_MODE must be 'entra' or 'password'.")

# --- Blob storage (§19–20): managed identity; Azurite only for local production-like runs ----- -
if env("BLOB_BACKEND", default="azure") != "azure":
    raise ImproperlyConfigured("BLOB_BACKEND must be 'azure' in production.")
BLOB_ACCOUNT_URL = env("BLOB_ACCOUNT_URL", default="")
BLOB_CONNECTION_STRING = env("BLOB_CONNECTION_STRING", default="")
if BLOB_CONNECTION_STRING and "AccountName=devstoreaccount1;" not in BLOB_CONNECTION_STRING:
    raise ImproperlyConfigured(
        "BLOB_CONNECTION_STRING (account keys) is refused in production: use BLOB_ACCOUNT_URL "
        "with the managed identity. Only the local Azurite emulator may use a connection string."
    )
if not (BLOB_ACCOUNT_URL or BLOB_CONNECTION_STRING):
    raise ImproperlyConfigured("BLOB_ACCOUNT_URL must be set in production.")

# --- OCR (§21): off by default, never the mock, Azure OpenAI fully configured ------------------
if env.bool("OCR_ENABLED", default=False):
    if env("OCR_PROVIDER", default="mock") == "mock":
        raise ImproperlyConfigured("OCR_PROVIDER must not be 'mock' when OCR is enabled.")
    if env("OCR_PROVIDER") == "azure_openai":
        for _name in (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION",
        ):
            _require(_name)

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

# --- HTTPS, cookies and security headers (TLS terminates at the Container Apps / SWA edge) ---- -
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SWA linked backend -> Container Apps ingress -> Django (Q-T13: NOT VERIFIED on Azure).
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=2)
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": TRUSTED_PROXY_COUNT}
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=True)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
MIDDLEWARE = [*MIDDLEWARE, "config.middleware.ContentSecurityPolicyMiddleware"]
# Same-origin through the Static Web Apps linked backend: no CORS middleware is installed.

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

# Request bodies: documents are streamed as multipart (MAX_UPLOAD_BYTES is enforced by the
# upload service); non-file payloads stay small.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# --- Telemetry (§38): Application Insights log handler, behind the national-ID masking filter - -
if env("APPLICATIONINSIGHTS_CONNECTION_STRING", default=""):
    LOGGING["handlers"]["telemetry"] = {
        "()": "config.telemetry.TelemetryLogHandler",
        "filters": ["mask_national_ids"],
    }
    LOGGING["root"]["handlers"] = [*LOGGING["root"]["handlers"], "telemetry"]
