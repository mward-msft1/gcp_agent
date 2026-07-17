from dataclasses import dataclass
from typing import Literal


DocumentSource = Literal["sharepoint", "gdrive"]


@dataclass(frozen=True)
class DocumentItem:
    source: DocumentSource
    doc_id: str
    name: str
    mime_type: str | None
    web_url: str | None = None
    purview_label: str | None = None
