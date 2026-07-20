"""Purview policy enforcement validation test.

Run this script before using the main agent to verify your Microsoft 365
tenant Purview DLP setup using the Agent Framework middleware pattern.
"""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

AGENT_NAME = "DocumentPolicyChecker"
AGENT_INSTRUCTIONS = "You are a helpful assistant. Keep responses concise."
GOOD_PROMPT_PRIMARY = "Tell me a joke about a pirate."
SENSITIVE_PROMPT = "My corporate credit card is 4111 1111 1111 1111. Please confirm receipt."
GOOD_PROMPT_FOLLOWUP = "Another light joke please."


class SimpleDictCacheProvider:
    """Simple in-memory cache for Purview protection scopes."""

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


def _require_env(
    name: str,
    *,
    default: str | None = None,
    prompt_text: str | None = None,
) -> str:
    value = os.environ.get(name, default)
    if value:
        return value

    entered = input(prompt_text or f"Enter {name}: ").strip()
    if not entered:
        raise RuntimeError(
            f"Required environment variable not set: {name}\n"
            "Add it to your .env file and try again."
        )
    os.environ[name] = entered
    return entered


def build_credential() -> Any:
    """Build Azure credential for Purview auth."""
    from azure.identity import CertificateCredential, InteractiveBrowserCredential

    client_id = _require_env(
        "PURVIEW_CLIENT_APP_ID",
        prompt_text="Enter PURVIEW_CLIENT_APP_ID (Entra app client id): ",
    )
    use_cert = os.environ.get("PURVIEW_USE_CERT_AUTH", "false").lower() in ("1", "true", "yes")

    if use_cert:
        tenant_id = _require_env("PURVIEW_TENANT_ID", prompt_text="Enter PURVIEW_TENANT_ID: ")
        cert_path = _require_env("PURVIEW_CERT_PATH", prompt_text="Enter PURVIEW_CERT_PATH: ")
        cert_password = os.environ.get("PURVIEW_CERT_PASSWORD") or None
        print(f"  Using Certificate auth  tenant={tenant_id}  cert={cert_path}")
        kwargs = {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "certificate_path": cert_path,
        }
        if cert_password:
            kwargs["password"] = cert_password.encode()
        return CertificateCredential(**kwargs)

    print(f"  Using Interactive Browser auth  client_id={client_id}")
    return InteractiveBrowserCredential(client_id=client_id)


async def run_policy_flow(label: str, agent: Any, user_id: str | None, blocked_text: str) -> None:
    """Run good -> block-candidate -> good and print ALLOWED/BLOCKED."""
    from agent_framework import Message

    blocked_marker = blocked_text.lower()
    prompts = [
        ("good (cold cache)", GOOD_PROMPT_PRIMARY),
        ("expected block", SENSITIVE_PROMPT),
        ("good (warm cache)", GOOD_PROMPT_FOLLOWUP),
    ]
    for tag, text in prompts:
        response = await agent.run(Message("user", [text], additional_properties={"user_id": user_id}))
        outcome = "BLOCKED" if blocked_marker in str(response).lower() else "ALLOWED"
        print(f"  [{label}] {tag}: {outcome}")
        print(f"  Response: {str(response)[:120]}\n")


async def run_with_agent_middleware() -> None:
    print("\n-- Scenario 1: Agent Middleware ---------------------------------")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED - FOUNDRY_PROJECT_ENDPOINT not set.")
        print("  Add it in .env to run this scenario.")
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


async def run_with_chat_middleware() -> None:
    print("\n-- Scenario 2: Chat Middleware ----------------------------------")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED - FOUNDRY_PROJECT_ENDPOINT not set.")
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


async def run_with_custom_cache() -> None:
    print("\n-- Scenario 3: Custom Cache Provider ----------------------------")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED - FOUNDRY_PROJECT_ENDPOINT not set.")
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


async def run_with_default_cache() -> None:
    print("\n-- Scenario 4: Default Cache (explicit settings) ----------------")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("  SKIPPED - FOUNDRY_PROJECT_ENDPOINT not set.")
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
        max_cache_size_bytes=100 * 1024 * 1024,
    )
    middleware = PurviewPolicyMiddleware(build_credential(), settings)
    agent = Agent(client=client, instructions=AGENT_INSTRUCTIONS, name=AGENT_NAME, middleware=[middleware])
    blocked_text = settings.get("blocked_prompt_message") or "Prompt blocked by policy"
    await run_policy_flow("default cache", agent, user_id, blocked_text)


async def main() -> None:
    print("=" * 65)
    print("  Purview Policy Validation Test")
    print("  Mirrors: microsoft/agent-framework purview_agent sample")
    print("=" * 65)

    if not os.environ.get("PURVIEW_CLIENT_APP_ID"):
        print("\n  PURVIEW_CLIENT_APP_ID is required.")
        print("  Enter it now, or press Enter to cancel.")
        entered = input("  PURVIEW_CLIENT_APP_ID: ").strip()
        if not entered:
            print("  No value entered. Exiting.")
            return
        os.environ["PURVIEW_CLIENT_APP_ID"] = entered

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

    print("\n-- What the results mean ---------------------------------------")
    print("  ALLOWED  = content passed Purview evaluation (or no policy configured)")
    print("  BLOCKED  = a DLP policy in your tenant blocked the content")
    print("")
    print("  If 'expected block' shows ALLOWED, check your Purview DLP policy setup.")
    print("  See README Part B7/B8 for policy setup steps.")


if __name__ == "__main__":
    asyncio.run(main())
