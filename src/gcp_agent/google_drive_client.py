import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from .models import DocumentItem

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveClient:
    def __init__(self, service_account_file: str, folder_id: str) -> None:
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=DRIVE_SCOPES
        )
        self._service = build("drive", "v3", credentials=credentials)
        self._folder_id = folder_id

    def list_documents(self) -> list[DocumentItem]:
        query = f"'{self._folder_id}' in parents and trashed = false"
        response = (
            self._service.files()
            .list(
                q=query,
                fields="files(id,name,mimeType,webViewLink)",
                pageSize=200,
            )
            .execute()
        )

        files = response.get("files", [])
        return [
            DocumentItem(
                source="gdrive",
                doc_id=item["id"],
                name=item["name"],
                mime_type=item.get("mimeType"),
                web_url=item.get("webViewLink"),
            )
            for item in files
        ]

    def download(self, file_id: str) -> bytes:
        request = self._service.files().get_media(fileId=file_id)
        stream = io.BytesIO()
        downloader = MediaIoBaseDownload(stream, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        return stream.getvalue()
