from __future__ import annotations

from app.infra.env import env_name


def _parse_csv(value: str | None) -> list[str]:
    """Parse a comma-separated string into a trimmed list."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _env_name() -> str:
    """Expose normalized environment name (kept for tests/backwards-compat)."""
    return env_name()


__all__ = ["_parse_csv", "_env_name"]
