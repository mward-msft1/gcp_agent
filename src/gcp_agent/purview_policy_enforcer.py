import asyncio

from .auth import EntraTokenProvider
from .config import Settings


class PurviewPolicyEnforcer:
    def __init__(self, settings: Settings, token_provider: EntraTokenProvider) -> None:
        self._enabled = settings.enable_purview_policy_enforcement
        self._default_user_id = settings.purview_default_user_id

        self._message_type = None
        self._activity_upload_text = None
        self._processor = None

        if not self._enabled:
            return

        if not self._default_user_id:
            raise ValueError(
                "PURVIEW_DEFAULT_USER_ID is required when ENABLE_PURVIEW_POLICY_ENFORCEMENT=true "
                "because this agent uses app-only Entra authentication."
            )

        try:
            from agent_framework import Message
            from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings
            from agent_framework_purview._client import PurviewClient
            from agent_framework_purview._models import Activity
            from agent_framework_purview._processor import ScopedContentProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Purview policy middleware dependencies are missing. Install "
                "`agent-framework` and `agent-framework-purview`."
            ) from exc

        purview_settings = PurviewSettings(
            app_name=settings.purview_app_name,
            tenant_id=settings.entra_tenant_id,
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION,
                location_value=settings.entra_client_id,
            ),
            blocked_prompt_message="Prompt blocked by policy",
            ignore_exceptions=settings.purview_ignore_exceptions,
            ignore_payment_required=settings.purview_ignore_payment_required,
        )
        client = PurviewClient(token_provider.credential, purview_settings)
        self._processor = ScopedContentProcessor(client, purview_settings)
        self._message_type = Message
        self._activity_upload_text = Activity.UPLOAD_TEXT

    def enforce_outbound_content(self, content: str, conversation_id: str) -> None:
        if not self._enabled:
            return
        if self._processor is None or self._message_type is None or self._activity_upload_text is None:
            raise RuntimeError("Purview policy enforcer was not initialized correctly.")

        additional_properties = {"user_id": self._default_user_id}
        message = self._message_type("user", [content], additional_properties=additional_properties)

        async def _check() -> bool:
            should_block, _ = await self._processor.process_messages(
                [message],
                self._activity_upload_text,
                session_id=conversation_id,
                user_id=self._default_user_id,
            )
            return should_block

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            should_block = asyncio.run(_check())
        else:
            raise RuntimeError(
                f"Purview policy enforcement cannot run with an active event loop ({loop}). "
                "Use an async flow or call this from synchronous runtime."
            )

        if should_block:
            raise RuntimeError("Blocked by Purview policy middleware evaluation.")
