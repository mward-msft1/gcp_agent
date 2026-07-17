import base64
import requests

from .auth import EntraTokenProvider


class GraphEmailClient:
    def __init__(self, sender_upn: str, token_provider: EntraTokenProvider) -> None:
        self._sender_upn = sender_upn
        self._token_provider = token_provider

    def send_with_attachment(
        self,
        recipient_email: str,
        subject: str,
        body_text: str,
        attachment_name: str,
        attachment_content: bytes,
        attachment_mime_type: str | None,
    ) -> None:
        token = self._token_provider.get_token(["https://graph.microsoft.com/.default"])
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": [{"emailAddress": {"address": recipient_email}}],
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": attachment_name,
                        "contentType": attachment_mime_type or "application/octet-stream",
                        "contentBytes": base64.b64encode(attachment_content).decode("utf-8"),
                    }
                ],
            },
            "saveToSentItems": "true",
        }

        response = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{self._sender_upn}/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Graph sendMail failed ({response.status_code}): {response.text}")
