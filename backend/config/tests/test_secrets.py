"""Key Vault settings loader (PROMPT.md §29). The SecretClient is mocked: NOT VERIFIED against
a real vault — requires Azure credentials."""

from unittest import mock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from django.core.exceptions import ImproperlyConfigured

from config import secrets

VAULT = "https://kv-medical-test.vault.azure.net/"


class FakeSecret:
    def __init__(self, value):
        self.value = value


@pytest.fixture
def vault(monkeypatch):
    for name in ("DJANGO_SECRET_KEY", "ENTRA_CLIENT_SECRET", "DATABASE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    stored: dict[str, str] = {}
    client = mock.MagicMock()

    def get_secret(name):
        if name not in stored:
            raise ResourceNotFoundError("SecretNotFound")
        return FakeSecret(stored[name])

    client.get_secret.side_effect = get_secret
    client.__enter__.return_value = client
    with mock.patch.object(secrets, "_secret_client", return_value=client) as factory:
        yield stored, client, factory


def test_reads_missing_names_from_the_vault(vault):
    stored, client, factory = vault
    stored["django-secret-key"] = "from-vault"
    values = secrets.load_secrets(["DJANGO_SECRET_KEY"], vault_url=VAULT)
    assert values == {"DJANGO_SECRET_KEY": "from-vault"}
    factory.assert_called_once_with(VAULT)
    client.get_secret.assert_called_once_with("django-secret-key")


def test_env_overrides_vault(vault, monkeypatch):
    stored, client, _ = vault
    stored["django-secret-key"] = "from-vault"
    monkeypatch.setenv("DJANGO_SECRET_KEY", "from-env")
    values = secrets.load_secrets(["DJANGO_SECRET_KEY"], vault_url=VAULT)
    assert values == {"DJANGO_SECRET_KEY": "from-env"}
    client.get_secret.assert_not_called()


def test_no_vault_url_means_environment_only(vault, monkeypatch):
    _, _, factory = vault
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "env-only")
    values = secrets.load_secrets(["ENTRA_CLIENT_SECRET", "DATABASE_PASSWORD"], vault_url="")
    assert values == {"ENTRA_CLIENT_SECRET": "env-only"}
    factory.assert_not_called()


def test_optional_secret_absent_everywhere_is_omitted(vault):
    values = secrets.load_secrets(["DATABASE_PASSWORD"], vault_url=VAULT)
    assert values == {}


def test_missing_required_secret_raises_improperly_configured(vault):
    with pytest.raises(ImproperlyConfigured, match="ENTRA_CLIENT_SECRET"):
        secrets.load_secrets(
            ["ENTRA_CLIENT_SECRET"], vault_url=VAULT, required=["ENTRA_CLIENT_SECRET"]
        )


def test_vault_access_error_is_improperly_configured_without_values(vault):
    _, client, _ = vault
    client.get_secret.side_effect = HttpResponseError("Forbidden by RBAC")
    with pytest.raises(ImproperlyConfigured, match="Key Vault") as exc:
        secrets.load_secrets(["DJANGO_SECRET_KEY"], vault_url=VAULT)
    assert "django-secret-key" in str(exc.value)


def test_vault_secret_names_use_dashes():
    assert secrets.vault_secret_name("ENTRA_CLIENT_SECRET") == "entra-client-secret"
