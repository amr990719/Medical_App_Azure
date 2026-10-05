"""Connection string for the LOCAL Azurite emulator (development and tests only).

`devstoreaccount1` and its key are Azurite's public, documented well-known development
credentials (also shipped inside azure-storage-blob); they are not a secret and only work against
a local emulator. The SDK's `UseDevelopmentStorage=true` shortcut is hard-wired to port 10000,
which is why the string is built here with a configurable port (decision D28).
"""

AZURITE_ACCOUNT = "devstoreaccount1"
AZURITE_ACCOUNT_KEY = (
    "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
)


def azurite_connection_string(port: int = 10000, host: str = "127.0.0.1") -> str:
    return (
        f"DefaultEndpointsProtocol=http;AccountName={AZURITE_ACCOUNT};"
        f"AccountKey={AZURITE_ACCOUNT_KEY};BlobEndpoint=http://{host}:{port}/{AZURITE_ACCOUNT};"
    )
