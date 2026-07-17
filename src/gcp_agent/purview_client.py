from azure.purview.catalog import PurviewCatalogClient

from .auth import EntraTokenProvider


class PurviewClient:
    def __init__(self, endpoint: str, token_provider: EntraTokenProvider) -> None:
        self._client = PurviewCatalogClient(
            endpoint=endpoint.rstrip("/"),
            credential=token_provider.credential,
        )

    def get_sensitivity_label(self, file_name: str) -> str | None:
        try:
            value = self._client.discovery.query({"keywords": file_name, "limit": 1})
        except Exception:
            return None

        entities = value.get("value", [])
        if not entities:
            return None

        entity = entities[0]
        return (
            entity.get("classification")
            or entity.get("description")
            or entity.get("name")
        )
