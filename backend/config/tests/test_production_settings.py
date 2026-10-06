"""Production settings must refuse to start when misconfigured (PROMPT.md §27, §30)."""

import importlib
import sys
from unittest import mock

import pytest
from azure.core.exceptions import ResourceNotFoundError
from django.core.exceptions import ImproperlyConfigured

VALID_ENV = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "ALLOWED_HOSTS": "api.example.test",
    "CSRF_TRUSTED_ORIGINS": "https://app.example.test",
    "DATABASE_URL": "postgres://id-medical@db.example.test:5432/medical",
    "BLOB_ACCOUNT_URL": "https://stmedical.blob.core.windows.net",
    "ENTRA_AUTHORITY": "https://tenant.ciamlogin.com/00000000-0000-0000-0000-000000000000",
    "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-0000000000c1",
    "ENTRA_CLIENT_SECRET": "entra-secret-from-key-vault-reference",
    "ENTRA_REDIRECT_URI": "https://app.example.test/api/v1/auth/callback/",
}


def load_production(monkeypatch, **overrides):
    # The surrounding environment (e.g. the docker compose dev container) must not leak in.
    inherited = (
        "DJANGO_SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "DATABASE_URL",
        "DEV_AUTH_ENABLED", "DEBUG", "OCR_ENABLED", "OCR_PROVIDER", "BLOB_BACKEND",
        "BLOB_CONNECTION_STRING", "BLOB_ACCOUNT_URL", "DB_AUTH_MODE", "DATABASE_PASSWORD",
        "DB_SSLMODE", "DB_CONN_MAX_AGE", "KEY_VAULT_URL", "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
        "ENTRA_AUTHORITY", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_REDIRECT_URI",
        "SECURE_HSTS_PRELOAD",
    )  # fmt: skip
    for key in inherited:
        monkeypatch.delenv(key, raising=False)
    for key, value in {**VALID_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    for name in ("config.settings.production", "config.settings.base"):
        sys.modules.pop(name, None)
    return importlib.import_module("config.settings.production")


@pytest.fixture(autouse=True)
def _restore_modules():
    yield
    for name in ("config.settings.production", "config.settings.base"):
        sys.modules.pop(name, None)


def test_valid_production_environment_loads(monkeypatch):
    prod = load_production(monkeypatch)
    assert prod.DEBUG is False
    assert prod.DEV_AUTH_ENABLED is False
    assert prod.ALLOWED_HOSTS == ["api.example.test"]
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SESSION_COOKIE_HTTPONLY is True
    assert prod.SESSION_COOKIE_SAMESITE == "Lax"
    assert prod.SECURE_HSTS_SECONDS >= 31536000
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "require"


def test_production_refuses_dev_auth(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DEV_AUTH_ENABLED"):
        load_production(monkeypatch, DEV_AUTH_ENABLED="true")


def test_production_refuses_debug(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DEBUG"):
        load_production(monkeypatch, DEBUG="true")


@pytest.mark.parametrize(
    "missing",
    [
        "DJANGO_SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "DATABASE_URL",
        "ENTRA_AUTHORITY", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_REDIRECT_URI",
    ],
)  # fmt: skip
def test_production_requires_setting(monkeypatch, missing):
    with pytest.raises(ImproperlyConfigured, match=missing):
        load_production(monkeypatch, **{missing: None})


def test_production_refuses_wildcard_hosts(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        load_production(monkeypatch, ALLOWED_HOSTS="*")


def test_production_refuses_short_secret_key(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        load_production(monkeypatch, DJANGO_SECRET_KEY="short")


def test_production_keeps_api_docs_off_and_content_short_lived(monkeypatch):
    for key in (
        "API_DOCS_ENABLED",
        "BLOB_BACKEND",
        "OCR_ENABLED",
        "OCR_PROVIDER",
        "BLOB_SAS_TTL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    prod = load_production(monkeypatch, BLOB_SAS_TTL_SECONDS="3600")
    assert prod.API_DOCS_ENABLED is False
    assert prod.BLOB_SAS_TTL_SECONDS == 300  # capped at 5 minutes whatever the environment says
    assert prod.ENTRA_ADMIN_REQUIRE_MFA is True


def test_production_refuses_the_in_memory_blob_backend(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="BLOB_BACKEND"):
        load_production(monkeypatch, BLOB_BACKEND="memory")


def test_production_refuses_mock_ocr_when_ocr_is_enabled(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="OCR_PROVIDER"):
        load_production(monkeypatch, OCR_ENABLED="true", OCR_PROVIDER="mock")


# --- Section 30 hardening ----------------------------------------------------------------------


def test_security_headers_and_hsts(monkeypatch):
    prod = load_production(monkeypatch)
    assert prod.SECURE_HSTS_SECONDS == 31536000
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert prod.SECURE_HSTS_PRELOAD is True
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert prod.SECURE_REFERRER_POLICY == "same-origin"
    assert prod.X_FRAME_OPTIONS == "DENY"
    assert "config.middleware.ContentSecurityPolicyMiddleware" in prod.MIDDLEWARE
    assert prod.MIDDLEWARE[0] == "config.middleware.HealthProbeMiddleware"
    assert prod.DATA_UPLOAD_MAX_MEMORY_SIZE <= 9 * 1024 * 1024
    assert not any("cors" in app for app in prod.INSTALLED_APPS)  # same-origin: no CORS at all


# --- Database authentication (PROMPT.md §26) ---------------------------------------------------


def test_entra_database_auth_is_the_default(monkeypatch):
    prod = load_production(monkeypatch, DB_CONN_MAX_AGE="3600")
    db = prod.DATABASES["default"]
    assert db["ENGINE"] == "config.db.entra_postgres"
    assert db["PASSWORD"] == ""
    assert db["USER"] == "id-medical"
    assert db["CONN_MAX_AGE"] <= 1800  # below the access-token lifetime
    assert db["OPTIONS"]["sslmode"] == "require"


def test_entra_database_auth_refuses_plaintext(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DB_SSLMODE"):
        load_production(monkeypatch, DB_SSLMODE="disable")


def test_password_mode_unchanged(monkeypatch):
    prod = load_production(
        monkeypatch,
        DB_AUTH_MODE="password",
        DATABASE_URL="postgres://medical:url-password@db.example.test:5432/medical",
    )
    db = prod.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["PASSWORD"] == "url-password"


def test_password_mode_takes_the_key_vault_password(monkeypatch):
    prod = load_production(monkeypatch, DB_AUTH_MODE="password", DATABASE_PASSWORD="kv-password")
    assert prod.DATABASES["default"]["PASSWORD"] == "kv-password"


def test_password_mode_without_a_password_refuses(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DATABASE_PASSWORD"):
        load_production(monkeypatch, DB_AUTH_MODE="password")


def test_unknown_database_auth_mode_refuses(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DB_AUTH_MODE"):
        load_production(monkeypatch, DB_AUTH_MODE="trust")


# --- Key Vault (PROMPT.md §29) -----------------------------------------------------------------


def test_secrets_come_from_key_vault_when_not_in_the_environment(monkeypatch):
    vault = {"django-secret-key": "v" * 64, "entra-client-secret": "kv-entra-secret"}

    class Secret:
        def __init__(self, value):
            self.value = value

    def get_secret(name):
        if name not in vault:
            raise ResourceNotFoundError("SecretNotFound")
        return Secret(vault[name])

    client = mock.MagicMock()
    client.__enter__.return_value = client
    client.get_secret.side_effect = get_secret
    with mock.patch("config.secrets._secret_client", return_value=client) as factory:
        prod = load_production(
            monkeypatch,
            KEY_VAULT_URL="https://kv-medical.vault.azure.net/",
            DJANGO_SECRET_KEY=None,
            ENTRA_CLIENT_SECRET=None,
        )
    factory.assert_called_once_with("https://kv-medical.vault.azure.net/")
    assert prod.SECRET_KEY == "v" * 64
    assert prod.ENTRA_CLIENT_SECRET == "kv-entra-secret"


# --- Blob storage (PROMPT.md §19–20) -----------------------------------------------------------


def test_blob_storage_requires_an_endpoint(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="BLOB_ACCOUNT_URL"):
        load_production(monkeypatch, BLOB_ACCOUNT_URL=None)


def test_blob_storage_refuses_account_keys(monkeypatch):
    connection = (
        "DefaultEndpointsProtocol=https;AccountName=stmedical;AccountKey=c2VjcmV0;"
        "EndpointSuffix=core.windows.net"
    )
    with pytest.raises(ImproperlyConfigured, match="managed identity"):
        load_production(monkeypatch, BLOB_CONNECTION_STRING=connection)


def test_blob_storage_accepts_the_local_azurite_emulator(monkeypatch):
    from apps.documents.azurite import azurite_connection_string

    connection = azurite_connection_string(10000, host="azurite")
    prod = load_production(monkeypatch, BLOB_ACCOUNT_URL=None, BLOB_CONNECTION_STRING=connection)
    assert connection == prod.BLOB_CONNECTION_STRING


# --- OCR (PROMPT.md §21) -------------------------------------------------------------------------


def test_azure_openai_ocr_requires_its_settings(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="AZURE_OPENAI_ENDPOINT"):
        load_production(monkeypatch, OCR_ENABLED="true", OCR_PROVIDER="azure_openai")


def test_azure_openai_ocr_configured(monkeypatch):
    prod = load_production(
        monkeypatch,
        OCR_ENABLED="true",
        OCR_PROVIDER="azure_openai",
        AZURE_OPENAI_ENDPOINT="https://aoai.openai.azure.com/",
        AZURE_OPENAI_DEPLOYMENT="vision",
        AZURE_OPENAI_API_VERSION="2024-10-21",
    )
    assert prod.OCR_ENABLED is True
    assert prod.OCR_PROVIDER == "azure_openai"


def test_ocr_can_be_switched_off_without_code_changes(monkeypatch):
    prod = load_production(monkeypatch, OCR_ENABLED="false", OCR_PROVIDER="azure_openai")
    assert prod.OCR_ENABLED is False


def test_entra_mode_with_injected_secrets_never_calls_key_vault(monkeypatch):
    # main.bicep: secrets arrive as Container Apps Key Vault references, DB_AUTH_MODE=entra.
    # No password is used in that mode, so a Key Vault hiccup must not stop a replica starting.
    with mock.patch("config.secrets._secret_client") as factory:
        prod = load_production(
            monkeypatch, KEY_VAULT_URL="https://kv-medical.vault.azure.net/", DB_AUTH_MODE="entra"
        )
    factory.assert_not_called()
    assert prod.DATABASES["default"]["ENGINE"] == "config.db.entra_postgres"


def test_password_mode_reads_the_password_from_key_vault(monkeypatch):
    client = mock.MagicMock()
    client.__enter__.return_value = client
    client.get_secret.return_value = mock.Mock(value="kv-db-password")
    with mock.patch("config.secrets._secret_client", return_value=client):
        prod = load_production(
            monkeypatch,
            KEY_VAULT_URL="https://kv-medical.vault.azure.net/",
            DB_AUTH_MODE="password",
        )
    client.get_secret.assert_called_once_with("database-password")
    assert prod.DATABASES["default"]["PASSWORD"] == "kv-db-password"


def test_production_trusts_the_swa_and_ingress_proxies_by_default(monkeypatch):
    prod = load_production(monkeypatch)
    assert prod.REST_FRAMEWORK["NUM_PROXIES"] == 2


def test_trusted_proxy_count_is_configurable(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    prod = load_production(monkeypatch)
    assert prod.REST_FRAMEWORK["NUM_PROXIES"] == 1
