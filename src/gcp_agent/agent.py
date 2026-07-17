from dataclasses import replace

from .auth import EntraTokenProvider
from .config import Settings
from .email_client import GraphEmailClient
from .google_drive_client import GoogleDriveClient
from .models import DocumentItem
from .purview_client import PurviewClient
from .sharepoint_client import SharePointClient


class DocumentRoutingAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        token_provider = EntraTokenProvider(
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_client_id,
            client_secret=settings.entra_client_secret,
        )

        self._sharepoint = SharePointClient(
            site_url=settings.sharepoint_site_url,
            folder_server_relative=settings.sharepoint_folder_server_relative,
            client_id=settings.entra_client_id,
            client_secret=settings.entra_client_secret,
        )
        self._gdrive = GoogleDriveClient(
            service_account_file=settings.google_drive_service_account_file,
            folder_id=settings.google_drive_folder_id,
        )
        self._email = GraphEmailClient(sender_upn=settings.graph_sender_upn, token_provider=token_provider)
        self._purview = PurviewClient(settings.purview_endpoint, token_provider) if settings.purview_endpoint else None

    def run_interactive(self) -> None:
        documents = self._inventory_documents()
        if not documents:
            raise RuntimeError("No documents were found in SharePoint or Google Drive.")

        self._print_inventory(documents)
        selected = self._prompt_document(documents)
        recipient = self._prompt_recipient()
        subject = self._prompt_subject(selected)
        self._enforce_send_policy(selected, recipient)

        attachment = self._download_document(selected)
        self._email.send_with_attachment(
            recipient_email=recipient,
            subject=subject,
            body_text=f"Attached document: {selected.name}",
            attachment_name=selected.name,
            attachment_content=attachment,
            attachment_mime_type=selected.mime_type,
        )
        print(f"Email sent to {recipient} with attachment '{selected.name}'.")

    def _inventory_documents(self) -> list[DocumentItem]:
        docs = self._sharepoint.list_documents() + self._gdrive.list_documents()
        if not self._purview:
            return docs

        enriched: list[DocumentItem] = []
        for doc in docs:
            label = self._purview.get_sensitivity_label(doc.name)
            enriched.append(replace(doc, purview_label=label))
        return enriched

    @staticmethod
    def _print_inventory(documents: list[DocumentItem]) -> None:
        print("Discovered documents:")
        for idx, doc in enumerate(documents, start=1):
            label_suffix = f" | Purview: {doc.purview_label}" if doc.purview_label else ""
            print(f"[{idx}] {doc.name} ({doc.source}){label_suffix}")

    @staticmethod
    def _prompt_document(documents: list[DocumentItem]) -> DocumentItem:
        while True:
            answer = input("Which document number should be attached? ").strip()
            if not answer.isdigit():
                print("Enter a valid number.")
                continue
            idx = int(answer)
            if idx < 1 or idx > len(documents):
                print("Selection out of range.")
                continue
            return documents[idx - 1]

    @staticmethod
    def _prompt_recipient() -> str:
        while True:
            recipient = input("Where should I send it (email address)? ").strip()
            if "@" in recipient and "." in recipient:
                return recipient
            print("Enter a valid email address.")

    @staticmethod
    def _prompt_subject(selected: DocumentItem) -> str:
        subject = input("Email subject (leave blank for default): ").strip()
        return subject or f"Requested document: {selected.name}"

    def _download_document(self, selected: DocumentItem) -> bytes:
        if selected.source == "sharepoint":
            return self._sharepoint.download(selected.doc_id)
        return self._gdrive.download(selected.doc_id)

    def _enforce_send_policy(self, selected: DocumentItem, recipient: str) -> None:
        if not selected.purview_label:
            return

        label = selected.purview_label.lower()
        is_blocked_label = any(token in label for token in self._settings.blocked_purview_labels)
        recipient_domain = recipient.rsplit("@", 1)[-1].lower()
        is_internal = recipient_domain in self._settings.allowed_recipient_domains

        if is_blocked_label and not is_internal:
            raise RuntimeError(
                f"Blocked by policy: document label '{selected.purview_label}' "
                f"cannot be sent to external domain '{recipient_domain}'."
            )
