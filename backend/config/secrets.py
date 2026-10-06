"""Key Vault-backed settings (PROMPT.md §29).

`load_secrets` returns the values of the requested setting names. The environment wins (in
Container Apps a secret is normally injected as a Key Vault *reference* resolved by the platform
with the managed identity); a name missing from the environment is read from `KEY_VAULT_URL`
with the shared managed-identity credential. Key Vault secret names cannot contain underscores:
`ENTRA_CLIENT_SECRET` is stored as `entra-client-secret`. Values are never logged or put in
exception messages.
"""

import os
from collections.abc import Iterable

from django.core.exceptions import ImproperlyConfigured


def vault_secret_name(setting_name: str) -> str:
    return setting_name.lower().replace("_", "-")


def _secret_client(vault_url: str):
    from azure.keyvault.secrets import SecretClient

    from config.azure import get_azure_credential

    return SecretClient(vault_url=vault_url, credential=get_azure_credential())


def load_secrets(
    names: Iterable[str], *, vault_url: str, required: Iterable[str] = ()
) -> dict[str, str]:
    names = list(names)
    values = {name: os.environ[name] for name in names if os.environ.get(name)}
    missing = [name for name in names if name not in values]
    if missing and vault_url:
        from azure.core.exceptions import AzureError, ResourceNotFoundError

        with _secret_client(vault_url) as client:
            for name in missing:
                secret_name = vault_secret_name(name)
                try:
                    value = client.get_secret(secret_name).value
                except ResourceNotFoundError:
                    continue
                except AzureError as exc:
                    raise ImproperlyConfigured(
                        f"Key Vault secret '{secret_name}' could not be read "
                        f"({type(exc).__name__}); check KEY_VAULT_URL and the managed "
                        "identity's 'Key Vault Secrets User' role."
                    ) from None
                if value:
                    values[name] = value
    for name in required:
        if not values.get(name):
            raise ImproperlyConfigured(
                f"{name} must be set in production (environment variable or Key Vault secret "
                f"'{vault_secret_name(name)}')."
            )
    return values
