from __future__ import annotations

from .defaults import DEFAULT_CLAIM_NAMESPACE


def claim_namespace(value: str | None) -> str:
    """Normalize namespace ensuring no trailing slash."""
    return (value or DEFAULT_CLAIM_NAMESPACE).rstrip("/")


def claim_uri(value: str | None, suffix: str) -> str:
    """Compose namespaced claim URI."""
    return f"{claim_namespace(value)}/{suffix}"
