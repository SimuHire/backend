"""Environment helpers shared across the app."""

from __future__ import annotations

import os

from app.core.settings import settings


def env_name() -> str:
    """Normalized environment name (lowercase)."""
    return str(getattr(settings, "ENV", os.getenv("ENV", "local"))).lower()


def is_local_or_test() -> bool:
    """Return True when running in local or test environments."""
    return env_name() in {"local", "test"}


def is_prod() -> bool:
    """Return True when running in production."""
    return env_name() == "prod"
