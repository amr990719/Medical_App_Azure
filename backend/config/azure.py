"""The one Azure credential of the process (PROMPT.md §4, §29).

In Azure Container Apps `DefaultAzureCredential` resolves to the app's managed identity
(`AZURE_CLIENT_ID` selects a user-assigned identity; set `AZURE_TOKEN_CREDENTIALS=prod` there to
keep developer credentials out of the chain). Locally it falls back to `az login`. Blob Storage,
Key Vault, PostgreSQL, Azure OpenAI and Application Insights share it, and with it one token
cache. Read from the environment, not Django settings: the Key Vault loader runs while the
settings module is still being imported.
"""

import os
from functools import lru_cache

from azure.core.credentials import TokenCredential


@lru_cache(maxsize=1)
def get_azure_credential() -> TokenCredential:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(
        managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID") or None
    )
