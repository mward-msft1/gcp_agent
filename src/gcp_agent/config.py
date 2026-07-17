from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    entra_tenant_id: str
    entra_client_id: str
    entra_client_secret: str
    sharepoint_site_url: str
    sharepoint_folder_server_relative: str
    graph_sender_upn: str
    google_drive_service_account_file: str
    google_drive_folder_id: str
    purview_endpoint: str | None = None
    allowed_recipient_domains: tuple[str, ...] = ()
    blocked_purview_labels: tuple[str, ...] = ("confidential", "secret", "restricted")
    enable_a365_observability: bool = True
    observability_service_name: str = "DocumentRoutingAgent"
    observability_service_namespace: str = "GCPAgent"

    @classmethod
    def from_env(cls) -> "Settings":
        def require(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                raise ValueError(f"Missing required environment variable: {name}")
            return value

        def parse_csv(name: str) -> tuple[str, ...]:
            value = os.getenv(name, "").strip()
            if not value:
                return ()
            return tuple(part.strip().lower() for part in value.split(",") if part.strip())

        def parse_bool(name: str, default: bool) -> bool:
            value = os.getenv(name, "").strip().lower()
            if not value:
                return default
            return value in {"1", "true", "yes", "on"}

        purview_endpoint = os.getenv("PURVIEW_ENDPOINT", "").strip() or None
        sender_upn = require("GRAPH_SENDER_UPN")
        sender_domain = sender_upn.rsplit("@", 1)[-1].lower()
        allowed_domains = parse_csv("ALLOWED_RECIPIENT_DOMAINS")
        if not allowed_domains:
            allowed_domains = (sender_domain,)

        return cls(
            entra_tenant_id=require("ENTRA_TENANT_ID"),
            entra_client_id=require("ENTRA_CLIENT_ID"),
            entra_client_secret=require("ENTRA_CLIENT_SECRET"),
            sharepoint_site_url=require("SHAREPOINT_SITE_URL"),
            sharepoint_folder_server_relative=require("SHAREPOINT_FOLDER_SERVER_RELATIVE"),
            graph_sender_upn=sender_upn,
            google_drive_service_account_file=require("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE"),
            google_drive_folder_id=require("GOOGLE_DRIVE_FOLDER_ID"),
            purview_endpoint=purview_endpoint,
            allowed_recipient_domains=allowed_domains,
            blocked_purview_labels=parse_csv("BLOCKED_PURVIEW_LABELS")
            or ("confidential", "secret", "restricted"),
            enable_a365_observability=parse_bool("ENABLE_A365_OBSERVABILITY", True),
            observability_service_name=os.getenv("OBSERVABILITY_SERVICE_NAME", "DocumentRoutingAgent"),
            observability_service_namespace=os.getenv("OBSERVABILITY_SERVICE_NAMESPACE", "GCPAgent"),
        )
