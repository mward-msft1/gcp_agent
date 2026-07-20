import os
import re

from dotenv import load_dotenv

from src.gcp_agent import DocumentRoutingAgent
from src.gcp_agent.a365 import configure_a365_observability
from src.gcp_agent.config import Settings


def main() -> None:
    load_dotenv()
    settings = _load_settings_interactive()
    configure_a365_observability(settings)
    agent = DocumentRoutingAgent(settings)
    agent.run_interactive()


def _load_settings_interactive() -> Settings:
    while True:
        try:
            return Settings.from_env()
        except ValueError as exc:
            message = str(exc)
            match = re.search(r"Missing required environment variable: ([A-Z0-9_]+)", message)
            if not match:
                raise

            env_name = match.group(1)
            entered = input(f"Enter required value for {env_name}: ").strip()
            if not entered:
                print(f"{env_name} cannot be empty. Please try again.")
                continue
            os.environ[env_name] = entered


if __name__ == "__main__":
    main()
