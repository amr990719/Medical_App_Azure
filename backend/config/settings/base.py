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
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
}
