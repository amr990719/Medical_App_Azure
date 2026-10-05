"""Local development settings (docker compose PostgreSQL + Azurite)."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-development-only")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Dev sign-in (pick a seeded user) — refused by production settings (PROMPT.md §27).
DEV_AUTH_ENABLED = env.bool("DEV_AUTH_ENABLED", default=True)
