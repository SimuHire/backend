from app.core.settings import settings


def perf_logging_enabled() -> bool:
    """Return True when perf debug logging is enabled."""
    return bool(getattr(settings, "DEBUG_PERF", False))


__all__ = ["perf_logging_enabled", "settings"]
