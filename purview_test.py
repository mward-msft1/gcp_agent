"""Purview policy enforcement validation test.

Run this script BEFORE using the main agent to verify that your Microsoft
365 tenant's Purview DLP policies are working correctly with the Agent
Framework middleware pattern.

This is adapted directly from:
  https://github.com/microsoft/agent-framework/tree/main/python/samples/05-end-to-end/purview_agent

It runs three message scenarios:
  1. good (cold cache)   - a normal safe message
  2. expected block      - a message containing a test credit card number
  3. good (warm cache)   - another normal message to confirm recovery

NOTE: The "expected block" will only show BLOCKED if your tenant has a
Purview DLP policy configured for "Microsoft 365 Copilot and AI apps"
that targets the Credit Card sensitive info type with a BLOCK action.
Without that policy, all three messages show ALLOWED – that is normal.

Required environment variables
--------------------------------
PURVIEW_CLIENT_APP_ID      Your Entra app registration client ID
                           (needs Graph delegated permissions for Purview)

Optional environment variables
--------------------------------
PURVIEW_USE_CERT_AUTH      Set to "true" to use certificate auth instead
                           of the browser pop-up
PURVIEW_TENANT_ID          Tenant GUID (required when cert auth is true)
PURVIEW_CERT_PATH          Full path to your .pfx certificate file
PURVIEW_CERT_PASSWORD      Certificate password (if encrypted)
PURVIEW_DEFAULT_USER_ID    Entra user object-ID GUID for policy evaluation
FOUNDRY_PROJECT_ENDPOINT   Azure AI Foundry endpoint (required to run
                           the full agent middleware scenarios)
FOUNDRY_MODEL              Model deployment name (default: gpt-4o-mini)
"""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Test prompts (same as the reference sample)
# ---------------------------------------------------------------------------

AGENT_NAME = "DocumentPolicyChecker"
AGENT_INSTRUCTIONS = "You are a helpful assistant. Keep responses concise."

GOOD_PROMPT_PRIMARY = "Tell me a joke about a pirate."
SENSITIVE_PROMPT = "My corporate credit card is 4111 1111 1111 1111. Please confirm receipt."
GOOD_PROMPT_FOLLOWUP = "Another light joke please."


# ---------------------------------------------------------------------------
# Custom cache provider (identical to SimpleDictCacheProvider in the sample)
# ---------------------------------------------------------------------------

class SimpleDictCacheProvider:
    """Simple in-memory cache for Purview protection scopes.

    Stores scope responses in a plain dict so they survive a single run.
    You can replace this with a Redis or Cosmos DB implementation for
    production use – just implement the same three async methods.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._access_count: dict[str, int] = {}

    async def get(self, key: str) -> Any | None:
        value = self._cache.get(key)
        if value is not None:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            print(f"  [Cache] HIT  {key[:60]}  (x{self._access_count[key]})")
        else:
            print(f"  [Cache] MISS {key[:60]}")
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._cache[key] = value
        print(f"  [Cache] SET  {key[:60]}  TTL={ttl_seconds}s")

    async def remove(self, key: str) -> None:
        self._cache.pop(key, None)
        self._access_count.pop(key, None)
        print(f"  [Cache] DEL  {key[:60]}")


# ---------------------------------------------------------------------------
# Credential builder (identical logic to build_credential() in the sample)
# ---------------------------------------------------------------------------

def _require_env(name: str, *, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if not val:
        raise RuntimeError(
            f"Required environment variable not set: {name}\n"
            f"Add it to your .env file and try again."
        )
    return val


def build_credential() -> Any:
    """Build an Azure credential for Purview authentication.

    Mode 1 – Interactive Browser (default, good for local testing):
        Set PURVIEW_CLIENT_APP_ID in .env.
        A browser window will open on first run so you can sign in.

    Mode 2 – Certificate (headless / production):
        Set PURVIEW_USE_CERT_AUTH=true, PURVIEW_TENANT_ID, PURVIEW_CERT_PATH.
    """
    from azure.identity import CertificateCredential, InteractiveBrowserCredential

    client_id = _require_env("PURVIEW_CLIENT_APP_ID")
    use_cert = os.environ.get("PURVIEW_USE_CERT_AUTH", "false").lower() in ("1", "true", "yes")

    if use_cert:
        tenant_id = _require_env("PURVIEW_TENANT_ID")
        cert_path = _require_env("PURVIEW_CERT_PATH")
        cert_password = os.environ.get("PURVIEW_CERT_PASSWORD") or None
        print(f"  Using Certificate auth  tenant={tenant_id}  cert={cert_path}")
        return CertificateCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            certificate_path=cert_path,
            password=cert_password.encode() if cert_password else None,
        )

    print(f"  Using Interactive Browser auth  client_id={client_id}")
    return InteractiveBrowserCredential(client_id=client_id)


# ---------------------------------------------------------------------------
# Policy flow runner (identical to run_policy_flow in the sample)
# ---------------------------------------------------------------------------

async def run_policy_flow(label: str, agent: Any, user_id: str | None, blocked_text: str) -> None:
    """Run good → block-candidate → good and print ALLOWED / BLOCKED per message."""
    from agent_framework import Message

    blocked_marker = blocked_text.lower()
    prompts = [
        ("good (cold cache)", GOOD_PROMPT_PRIMARY),
        ("expected block",    SENSITIVE_PROMPT),
        ("good (warm cache)", GOOD_PROMPT_FOLLOWUP),
    ]
    for tag, text in prompts:
        response = await agent.run(
            Message("user", [text], additional_properties={"user_id": user_id})
        )
        outcome = "BLOCKED" if blocked_marker in str(response).lower() else "ALLOWED"
        print(f"  [{label}] {tag}: {outcome}")
        print(f"  Response: {str(response)[:120]}\n")


# ---------------------------------------------------------------------------
# Scenario 1 – Agent-level middleware
# ---------------------------------------------------------------------------

async def run_with_agent_middleware() -> None:
    """Attach PurviewPolicyMiddleware directly to an Agent (agent-level check)."""
    print("\n── Scenario 1: Agent Middleware ──────────────────────────────────")

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED – FOUNDRY_PROJECT_ENDPOINT not set.")
        print("  Add your Azure AI Foundry endpoint to .env to run this scenario.")
        return

    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
    from azure.identity import AzureCliCredential

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")

    client = FoundryChatClient(model=deployment, project_endpoint=endpoint, credential=AzureCliCredential())
    settings = PurviewSettings(app_name="DocumentRoutingAgent")
    middleware = PurviewPolicyMiddleware(build_credential(), settings)
    agent = Agent(client=client, instructions=AGENT_INSTRUCTIONS, name=AGENT_NAME, middleware=[middleware])

    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("agent middleware", agent, user_id, blocked_text)


# ---------------------------------------------------------------------------
# Scenario 2 – Chat-client-level middleware
# ---------------------------------------------------------------------------

async def run_with_chat_middleware() -> None:
    """Attach PurviewChatPolicyMiddleware at the chat client level."""
    print("\n── Scenario 2: Chat Middleware ───────────────────────────────────")

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED – FOUNDRY_PROJECT_ENDPOINT not set.")
        return

    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from agent_framework.microsoft import PurviewChatPolicyMiddleware, PurviewSettings
    from azure.identity import AzureCliCredential

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")

    settings = PurviewSettings(app_name="DocumentRoutingAgent (Chat)")
    client = FoundryChatClient(
        model=deployment,
        project_endpoint=endpoint,
        credential=AzureCliCredential(),
        middleware=[PurviewChatPolicyMiddleware(build_credential(), settings)],
    )
    agent = Agent(client=client, instructions=AGENT_INSTRUCTIONS, name=AGENT_NAME)

    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("chat middleware", agent, user_id, blocked_text)


# ---------------------------------------------------------------------------
# Scenario 3 – Custom cache provider
# ---------------------------------------------------------------------------

async def run_with_custom_cache() -> None:
    """Use the SimpleDictCacheProvider to see Cache HIT / MISS traces."""
    print("\n── Scenario 3: Custom Cache Provider ────────────────────────────")

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED – FOUNDRY_PROJECT_ENDPOINT not set.")
        return

    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
    from azure.identity import AzureCliCredential

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")

    client = FoundryChatClient(model=deployment, project_endpoint=endpoint, credential=AzureCliCredential())
    cache = SimpleDictCacheProvider()
    settings = PurviewSettings(app_name="DocumentRoutingAgent (Custom Cache)")
    middleware = PurviewPolicyMiddleware(build_credential(), settings, cache_provider=cache)
    agent = Agent(client=client, instructions=AGENT_INSTRUCTIONS, name=AGENT_NAME, middleware=[middleware])

    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("custom cache", agent, user_id, blocked_text)


# ---------------------------------------------------------------------------
# Scenario 4 – Default built-in cache with explicit TTL/size settings
# ---------------------------------------------------------------------------

async def run_with_default_cache() -> None:
    """Use built-in InMemoryCacheProvider with explicit TTL and size limits."""
    print("\n── Scenario 4: Default Cache (explicit settings) ─────────────────")

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED – FOUNDRY_PROJECT_ENDPOINT not set.")
        return

    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
    from azure.identity import AzureCliCredential

    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")
    user_id = os.environ.get("PURVIEW_DEFAULT_USER_ID")

    client = FoundryChatClient(model=deployment, project_endpoint=endpoint, credential=AzureCliCredential())
    settings = PurviewSettings(
        app_name="DocumentRoutingAgent (Default Cache)",
        cache_ttl_seconds=3600,
        max_cache_size_bytes=100 * 1024 * 1024,  # 100 MB
    )
    middleware = PurviewPolicyMiddleware(build_credential(), settings)
    agent = Agent(client=client, instructions=AGENT_INSTRUCTIONS, name=AGENT_NAME, middleware=[middleware])

    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("default cache", agent, user_id, blocked_text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 65)
    print("  Purview Policy Validation Test")
    print("  Mirrors: microsoft/agent-framework purview_agent sample")
    print("=" * 65)

    # Check minimum required env var
    if not os.environ.get("PURVIEW_CLIENT_APP_ID"):
        print(
            "\n  ERROR: PURVIEW_CLIENT_APP_ID is not set.\n"
            "  Add it to your .env file and run again.\n"
            "  See README – Part B2 or Part B8 for how to get it."
        )
        return

    for scenario in [
        run_with_agent_middleware,
        run_with_chat_middleware,
        run_with_custom_cache,
        run_with_default_cache,
    ]:
        try:
            await scenario()
        except Exception as exc:
            print(f"  ERROR in {scenario.__name__}: {exc}\n")

    print("\n── What the results mean ────────────────────────────────────────")
    print("  ALLOWED  = content passed Purview evaluation (or no policy configured)")
    print("  BLOCKED  = a DLP policy in your tenant blocked the content")
    print("")
    print("  If 'expected block' shows ALLOWED, check that your tenant has a")
    print("  Purview DLP policy for 'Microsoft 365 Copilot and AI apps' with a")
    print("  BLOCK rule on the 'Credit Card Number' sensitive info type.")
    print("  See README Part B7 for detailed Purview DLP policy setup steps.")


if __name__ == "__main__":
    asyncio.run(main())
