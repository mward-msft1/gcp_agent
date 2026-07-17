from .config import Settings

try:
    from microsoft_agents_a365.observability.core.config import configure
except ImportError:  # pragma: no cover
    configure = None


def configure_a365_observability(settings: Settings) -> None:
    if not settings.enable_a365_observability:
        return
    if configure is None:
        raise RuntimeError(
            "Agent365 SDK observability package is missing. "
            "Install microsoft-agents-a365-observability-core."
        )
    configure(
        service_name=settings.observability_service_name,
        service_namespace=settings.observability_service_namespace,
    )
