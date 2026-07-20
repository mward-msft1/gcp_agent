"""Purview policy enforcement for the Document Routing Agent.

This module wires Microsoft Purview DLP policy evaluation (via the
microsoft/agent-framework Purview middleware pattern) into the outbound
send workflow.  It mirrors the approach from:
  https://github.com/microsoft/agent-framework/tree/main/python/samples/05-end-to-end/purview_agent

Two credential modes are supported (controlled by env vars):
  - Interactive Browser  (default, good for local testing)
  - Certificate          (headless / CI / production)

Set ENABLE_PURVIEW_POLICY_ENFORCEMENT=true to activate.
"""
import asyncio
import os
from typing import Any

from .auth import EntraTokenProvider
from .config import Settings


# ---------------------------------------------------------------------------
# Custom cache provider (mirrors SimpleDictCacheProvider from the sample)
# ---------------------------------------------------------------------------

class SimpleDictCacheProvider:
    """In-memory cache provider with optional hit/miss logging.

    Implements the CacheProvider protocol required by PurviewPolicyMiddleware.
    You can swap this for any external store (Redis, Cosmos DB, etc.) by
    implementing the same three async methods.
    """

    def __init__(self, verbose: bool = False) -> None:
        self._cache: dict[str, Any] = {}
        self._access_count: dict[str, int] = {}
        self._verbose = verbose

    async def get(self, key: str) -> Any | None:
        value = self._cache.get(key)
        if value is not None:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            if self._verbose:
                print(f"[PurviewCache] HIT  {key[:60]}  (x{self._access_count[key]})")
        else:
            if self._verbose:
                print(f"[PurviewCache] MISS {key[:60]}")
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._cache[key] = value
        if self._verbose:
            print(f"[PurviewCache] SET  {key[:60]}  TTL={ttl_seconds}s")

    async def remove(self, key: str) -> None:
        self._cache.pop(key, None)
        self._access_count.pop(key, None)
        if self._verbose:
            print(f"[PurviewCache] DEL  {key[:60]}")


# ---------------------------------------------------------------------------
# Credential builder (mirrors build_credential() from the sample)
# ---------------------------------------------------------------------------

def build_purview_credential(
    client_id: str,
    *,
    use_cert_auth: bool = False,
    tenant_id: str | None = None,
    cert_path: str | None = None,
    cert_password: str | None = None,
) -> Any:
    """Return an Azure credential for Purview authentication.

    Modes
    -----
    Interactive Browser (default)
        Opens a browser on first run so you sign in with your own account.
        Good for local testing.  Set PURVIEW_CLIENT_APP_ID to your Entra
        app registration's client ID.

    Certificate (headless / production)
        Set PURVIEW_USE_CERT_AUTH=true, plus PURVIEW_TENANT_ID and
        PURVIEW_CERT_PATH.  The .pfx must contain both cert + private key.
    """
    try:
        from azure.identity import CertificateCredential, InteractiveBrowserCredential
    except ImportError as exc:
        raise RuntimeError("Install `azure-identity` to use Purview credential.") from exc

    if use_cert_auth:
        if not tenant_id or not cert_path:
            raise ValueError(
                "PURVIEW_TENANT_ID and PURVIEW_CERT_PATH are required when "
                "PURVIEW_USE_CERT_AUTH=true"
            )
        print(f"[Purview] Using Certificate auth  tenant={tenant_id}  cert={cert_path}")
        return CertificateCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            certificate_path=cert_path,
            password=cert_password.encode() if cert_password else None,
        )

    print(f"[Purview] Using Interactive Browser auth  client_id={client_id}")
    return InteractiveBrowserCredential(client_id=client_id)


# ---------------------------------------------------------------------------
# Policy enforcer
# ---------------------------------------------------------------------------

class PurviewPolicyEnforcer:
    """Wraps Purview DLP policy evaluation for outbound document sends.

    When ENABLE_PURVIEW_POLICY_ENFORCEMENT=true the agent will call the
    Microsoft Graph dataSecurityAndGovernance endpoints BEFORE sending the
    email.  If any DLP policy matches and its action is BLOCK, the send is
    aborted with a clear error message.

    This follows the middleware pattern from:
      agent_framework.microsoft.PurviewPolicyMiddleware
    but applies it inline in a synchronous CLI flow so no separate web
    server or Agent runtime is required.
    """

    def __init__(self, settings: Settings, token_provider: EntraTokenProvider) -> None:
        self._enabled = settings.enable_purview_policy_enforcement
        self._default_user_id = settings.purview_default_user_id
        self._processor = None
        self._Message = None
        self._Activity = None

        if not self._enabled:
            return

        if not self._default_user_id:
            raise ValueError(
                "PURVIEW_DEFAULT_USER_ID is required when "
                "ENABLE_PURVIEW_POLICY_ENFORCEMENT=true.  "
                "Set it to a real Entra user object-ID GUID."
            )

        try:
            from agent_framework import Message  # noqa: F401
            from agent_framework_purview import (
                PurviewAppLocation,
                PurviewLocationType,
                PurviewSettings,
            )
            from agent_framework_purview._client import PurviewClient
            from agent_framework_purview._models import Activity
            from agent_framework_purview._processor import ScopedContentProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Purview policy middleware packages are missing.\n"
                "Run:  pip install agent-framework agent-framework-purview"
            ) from exc

        # Build credential from env vars (mirrors build_credential in the sample)
        client_id = os.getenv("PURVIEW_CLIENT_APP_ID") or settings.entra_client_id
        use_cert = os.getenv("PURVIEW_USE_CERT_AUTH", "false").lower() in ("1", "true", "yes")
        credential = build_purview_credential(
            client_id=client_id,
            use_cert_auth=use_cert,
            tenant_id=os.getenv("PURVIEW_TENANT_ID") or settings.entra_tenant_id,
            cert_path=os.getenv("PURVIEW_CERT_PATH"),
            cert_password=os.getenv("PURVIEW_CERT_PASSWORD"),
        )

        purview_settings = PurviewSettings(
            app_name=settings.purview_app_name,
            tenant_id=settings.entra_tenant_id,
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION,
                location_value=settings.entra_client_id,
            ),
            blocked_prompt_message="Prompt blocked by Purview policy",
            ignore_exceptions=settings.purview_ignore_exceptions,
            ignore_payment_required=settings.purview_ignore_payment_required,
            cache_ttl_seconds=1800,
        )

        # Use the custom cache provider (matches SimpleDictCacheProvider from the sample)
        cache = SimpleDictCacheProvider(verbose=True)

        client = PurviewClient(credential, purview_settings)
        self._processor = ScopedContentProcessor(client, purview_settings, cache)

        from agent_framework import Message as _Msg
        self._Message = _Msg
        self._Activity = Activity

    def enforce_outbound_content(self, content: str, conversation_id: str) -> None:
        """Synchronously check content against tenant DLP policies.

        Raises RuntimeError if blocked.  No-ops when enforcement is disabled.
        """
        if not self._enabled:
            return
        if self._processor is None:
            raise RuntimeError("PurviewPolicyEnforcer not initialised correctly.")

        msg = self._Message(
            "user",
            [content],
            additional_properties={"user_id": self._default_user_id},
        )

        async def _check() -> bool:
            should_block, _ = await self._processor.process_messages(
                [msg],
                self._Activity.UPLOAD_TEXT,
                session_id=conversation_id,
                user_id=self._default_user_id,
            )
            return should_block

        try:
            asyncio.get_running_loop()
            # Already inside an event loop – should not happen in CLI mode
            raise RuntimeError(
                "Purview check cannot run inside an active event loop.  "
                "Call from synchronous code only."
            )
        except RuntimeError as exc:
            if "no current event loop" in str(exc).lower() or "no running event loop" in str(exc).lower():
                should_block = asyncio.run(_check())
            else:
                raise

        if should_block:
            raise RuntimeError(
                "SEND BLOCKED: Purview DLP policy evaluation flagged this content "
                "as restricted.  The email was NOT sent."
            )
