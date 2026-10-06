"""Local development settings (docker compose PostgreSQL + Azurite)."""

from apps.documents.azurite import azurite_connection_string
from config.envfile import read_env_file

from .base import *  # noqa: F403
from .base import BASE_DIR, env

# The repository-root `.env` (gitignored) holds local overrides shared with docker compose.
# Empty values are skipped, so a copy of `.env.example` keeps every default.
read_env_file(BASE_DIR.parent / ".env")

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-development-only")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"]
)

# Dev sign-in (pick a seeded user) — refused by production settings (PROMPT.md §27).
DEV_AUTH_ENABLED = env.bool("DEV_AUTH_ENABLED", default=True)
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)

# Local Azurite (public emulator credentials, see apps/documents/azurite.py). Inside docker
# compose the emulator is reached by its service name (AZURITE_BLOB_HOST=azurite).
BLOB_CONNECTION_STRING = env(
    "BLOB_CONNECTION_STRING",
    default=azurite_connection_string(
        env.int("AZURITE_BLOB_PORT", default=10000),
        host=env("AZURITE_BLOB_HOST", default="127.0.0.1"),
    ),
)
BLOB_CREATE_CONTAINER = env.bool("BLOB_CREATE_CONTAINER", default=True)

# OCR with the deterministic mock provider (production uses OCR_PROVIDER=azure_openai).
OCR_ENABLED = env.bool("OCR_ENABLED", default=True)
OCR_PROVIDER = env("OCR_PROVIDER", default="mock")
