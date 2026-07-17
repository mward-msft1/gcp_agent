from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.files.file import File

from .models import DocumentItem


class SharePointClient:
    def __init__(self, site_url: str, folder_server_relative: str, client_id: str, client_secret: str) -> None:
        self._folder_server_relative = folder_server_relative
        self._ctx = ClientContext(site_url).with_credentials(ClientCredential(client_id, client_secret))

    def list_documents(self) -> list[DocumentItem]:
        folder = self._ctx.web.get_folder_by_server_relative_url(self._folder_server_relative)
        files = folder.files
        self._ctx.load(files)
        self._ctx.execute_query()

        return [
            DocumentItem(
                source="sharepoint",
                doc_id=f.serverRelativeUrl,
                name=f.name,
                mime_type=None,
                web_url=f.serverRelativeUrl,
            )
            for f in files
        ]

    def download(self, server_relative_url: str) -> bytes:
        response = File.open_binary(self._ctx, server_relative_url)
        return response.content
