"""Test settings: PostgreSQL only (never SQLite), fast hashing, deterministic flags."""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "django-insecure-test-only"  # noqa: S105
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DEV_AUTH_ENABLED = True
OCR_ENABLED = False
OCR_PROVIDER = "mock"

# Business defaults pinned so tests do not depend on the developer's environment.
CURRENT_FISCAL_YEAR = 2026
MAX_BENEFICIARIES = 10
REQUIRE_MEMBER_PHOTO = False
CHILD_NATIONAL_ID_AGE = 16
ENFORCE_SPOUSE_GENDER = True
ENFORCE_SON_MINOR_AGE = True
SON_MINOR_MAX_AGE = 18

API_DOCS_ENABLED = True
BLOB_BACKEND = "memory"
DOCUMENT_CONTENT_DELIVERY = "stream"
ALLOW_PDF_DOCUMENTS = False
ALLOW_HEIC = False
MALWARE_SCAN_ENABLED = False
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ENTRA_AUTHORITY = ""
ENTRA_ADMIN_REQUIRE_MFA = True
