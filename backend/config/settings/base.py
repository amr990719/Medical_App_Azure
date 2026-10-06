"""Settings shared by every environment (PROMPT.md §30).

Environment-specific modules (`development`, `test`, `production`) import everything from here
and override what differs. Values come from environment variables only; no secrets in code.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# --- Core -------------------------------------------------------------------------------------

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY", default=None)
ALLOWED_HOSTS: list[str] = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    # Project apps. `accounts` first: AUTH_USER_MODEL must exist before anything references it.
    "apps.accounts",
    "apps.reference",
    "apps.doctors",
    "apps.fees",
    "apps.applications",
    "apps.beneficiaries",
    "apps.documents",
    "apps.ocr",
    "apps.audit",
]

MIDDLEWARE = [
    "config.middleware.HealthProbeMiddleware",  # probes skip host validation and redirects
    "config.middleware.RequestIdMiddleware",
    "config.middleware.RequestBodyLimitMiddleware",  # 413 before an oversized body is read
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AbsoluteSessionTimeoutMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

AUTH_USER_MODEL = "accounts.User"
# No password sign-in anywhere (Entra External ID / dev login only); the backend only restores
# the session user and refuses inactive accounts.
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.SessionOnlyBackend"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # every project model declares a UUID pk

# --- Database (PostgreSQL only — dev, test, CI and production) ---------------------------------

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://medical:medical@localhost:5432/medical")
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["OPTIONS"] = {"sslmode": env("DB_SSLMODE", default="prefer")}

# --- I18N ---------------------------------------------------------------------------------------

LANGUAGE_CODE = "ar"
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Business configuration (docs/business-rules.md §10) ---------------------------------------

# The fiscal year is a deliberate setting, not derived from the clock (decision D4).
CURRENT_FISCAL_YEAR: int = env.int("CURRENT_FISCAL_YEAR", default=2026)
MAX_BENEFICIARIES: int = env.int("MAX_BENEFICIARIES", default=10)
REQUIRE_MEMBER_PHOTO: bool = env.bool("REQUIRE_MEMBER_PHOTO", default=False)
CHILD_NATIONAL_ID_AGE: int = env.int("CHILD_NATIONAL_ID_AGE", default=16)
ENFORCE_SPOUSE_GENDER: bool = env.bool("ENFORCE_SPOUSE_GENDER", default=True)
ENFORCE_SON_MINOR_AGE: bool = env.bool("ENFORCE_SON_MINOR_AGE", default=True)
SON_MINOR_MAX_AGE: int = env.int("SON_MINOR_MAX_AGE", default=18)

# --- Feature flags --------------------------------------------------------------------------------

DEV_AUTH_ENABLED = False  # only development/test settings may turn this on
OCR_ENABLED: bool = env.bool("OCR_ENABLED", default=False)
OCR_PROVIDER: str = env("OCR_PROVIDER", default="mock")

# --- Logging: JSON to stdout, every record passes the national-ID masking filter --------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"mask_national_ids": {"()": "config.logging.NationalIdMaskingFilter"}},
    "formatters": {"json": {"()": "config.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["mask_national_ids"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    # The Azure SDK logs every HTTP request at INFO (URLs, headers): keep it to warnings.
    "loggers": {"azure": {"level": "WARNING"}},
}

# --- Sessions and CSRF (BFF pattern, PROMPT.md §27) ---------------------------------------------

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Idle timeout: the expiry is renewed on every request. Absolute timeout: enforced by
# AbsoluteSessionTimeoutMiddleware from the sign-in time stored in the session.
SESSION_COOKIE_AGE = env.int("SESSION_IDLE_TIMEOUT_SECONDS", default=2 * 60 * 60)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_ABSOLUTE_TIMEOUT_SECONDS: int = env.int(
    "SESSION_ABSOLUTE_TIMEOUT_SECONDS", default=12 * 60 * 60
)
CSRF_COOKIE_HTTPONLY = False  # the SPA reads `csrftoken` and sends it as X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_USE_SESSIONS = False

# --- Cache (throttling). Production overrides with a cache shared by every replica. -----------

CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

# --- Django REST Framework ----------------------------------------------------------------------

# Proxies in front of Django that append to X-Forwarded-For (production: Static Web Apps linked
# backend + Container Apps ingress). Only their entries are trusted for the client address used
# by throttles and the audit hash; 0 ignores the header (direct connections, local development).
TRUSTED_PROXY_COUNT: int = env.int("TRUSTED_PROXY_COUNT", default=0)

REST_FRAMEWORK = {
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
    "DEFAULT_AUTHENTICATION_CLASSES": ["config.api.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.IsAuthenticatedActive"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.api.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.api.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth_callback": env("AUTH_CALLBACK_RATE_LIMIT", default="20/min"),
        "dev_login": "30/min",
        "uploads": env("UPLOAD_RATE_LIMIT", default="60/hour"),
        "ocr": env("OCR_RATE_LIMIT", default="30/hour"),
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Medical Syndicates Treatment Project API",
    "DESCRIPTION": "مشروع علاج أعضاء النقابات الطبية — REST API (session cookie + CSRF).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "ApplicationStatusEnum": "apps.reference.constants.ApplicationStatus",
        "PaymentStatusEnum": "apps.reference.constants.PaymentStatus",
        "DocumentTypeEnum": "apps.reference.constants.DocumentType",
        "KinshipEnum": "apps.reference.constants.Kinship",
    },
}
API_DOCS_ENABLED: bool = env.bool("API_DOCS_ENABLED", default=False)

# --- Documents and Blob Storage (PROMPT.md §19–20) -----------------------------------------------

# "azure": Azure Blob (connection string locally/Azurite, account URL + managed identity in
# Azure). "memory": process-local store for unit tests only.
BLOB_BACKEND: str = env("BLOB_BACKEND", default="azure")
BLOB_CONNECTION_STRING: str = env("BLOB_CONNECTION_STRING", default="")
BLOB_ACCOUNT_URL: str = env("BLOB_ACCOUNT_URL", default="")
BLOB_CONTAINER: str = env("BLOB_CONTAINER", default="medical-documents")
BLOB_CREATE_CONTAINER: bool = env.bool("BLOB_CREATE_CONTAINER", default=False)  # Bicep creates it
# Content delivery: "stream" (authorized proxy through Django) or "sas" (302 to a read-only SAS).
DOCUMENT_CONTENT_DELIVERY: str = env("DOCUMENT_CONTENT_DELIVERY", default="stream")
BLOB_SAS_TTL_SECONDS: int = min(env.int("BLOB_SAS_TTL_SECONDS", default=300), 300)
BLOB_CLEANUP_GRACE_HOURS: int = env.int("BLOB_CLEANUP_GRACE_HOURS", default=24)
MAX_UPLOAD_BYTES: int = env.int("MAX_UPLOAD_BYTES", default=8 * 1024 * 1024)
# Room for the multipart boundaries and the other form fields around one file.
MULTIPART_OVERHEAD_BYTES = 256 * 1024
RECEIPT_MIN_WIDTH: int = 400
RECEIPT_MIN_HEIGHT: int = 300
ALLOW_PDF_DOCUMENTS: bool = env.bool("ALLOW_PDF_DOCUMENTS", default=False)
ALLOW_HEIC: bool = env.bool("ALLOW_HEIC", default=False)
MALWARE_SCAN_ENABLED: bool = env.bool("MALWARE_SCAN_ENABLED", default=False)
# Larger multipart bodies are streamed to a temporary file, never kept in memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# --- OCR (PROMPT.md §21) --------------------------------------------------------------------------

AZURE_OPENAI_ENDPOINT: str = env("AZURE_OPENAI_ENDPOINT", default="")
AZURE_OPENAI_DEPLOYMENT: str = env("AZURE_OPENAI_DEPLOYMENT", default="")
AZURE_OPENAI_API_VERSION: str = env("AZURE_OPENAI_API_VERSION", default="")

# --- Microsoft Entra External ID (OIDC BFF, PROMPT.md §27) ----------------------------------------

# Authority of the external tenant, e.g. https://<subdomain>.ciamlogin.com/<tenant-id>
ENTRA_AUTHORITY: str = env("ENTRA_AUTHORITY", default="")
ENTRA_TENANT_ID: str = env("ENTRA_TENANT_ID", default="")
ENTRA_CLIENT_ID: str = env("ENTRA_CLIENT_ID", default="")
ENTRA_CLIENT_SECRET: str = env("ENTRA_CLIENT_SECRET", default="")  # Key Vault reference in Azure
ENTRA_REDIRECT_URI: str = env("ENTRA_REDIRECT_URI", default="")
ENTRA_POST_LOGOUT_REDIRECT_URI: str = env("ENTRA_POST_LOGOUT_REDIRECT_URI", default="")
ENTRA_SCOPES: list[str] = env.list("ENTRA_SCOPES", default=[])  # openid/profile added by MSAL
ENTRA_ADMIN_REQUIRE_MFA: bool = env.bool("ENTRA_ADMIN_REQUIRE_MFA", default=True)
ENTRA_CLOCK_SKEW_SECONDS: int = 120
CSRF_FAILURE_VIEW = "config.api.views.csrf_failure"
# Normally discovered from `{ENTRA_AUTHORITY}/v2.0/.well-known/openid-configuration`.
ENTRA_ISSUER: str = env("ENTRA_ISSUER", default="")
ENTRA_JWKS_URI: str = env("ENTRA_JWKS_URI", default="")
# Decoded-image size cap (decompression-bomb guard), well below Pillow's own 89 MP warning.
DOCUMENT_MAX_PIXELS: int = env.int("DOCUMENT_MAX_PIXELS", default=40_000_000)
