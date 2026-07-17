from azure.identity import ClientSecretCredential


class EntraTokenProvider:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

    def get_token(self, scopes: list[str]) -> str:
        token = self._credential.get_token(*scopes)
        return token.token

    @property
    def credential(self) -> ClientSecretCredential:
        return self._credential
