from dotenv import load_dotenv

from src.gcp_agent import DocumentRoutingAgent
from src.gcp_agent.a365 import configure_a365_observability
from src.gcp_agent.config import Settings


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    configure_a365_observability(settings)
    agent = DocumentRoutingAgent(settings)
    agent.run_interactive()


if __name__ == "__main__":
    main()
