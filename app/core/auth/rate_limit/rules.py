from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Request

from app.core.env import is_local_or_test
from app.core.settings import settings

DEFAULT_RATE_LIMIT_DETAIL = "Too many requests. Please slow down."


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: float


def rate_limit_enabled() -> bool:
    if settings.RATE_LIMIT_ENABLED is not None:
        return bool(settings.RATE_LIMIT_ENABLED)
    return not is_local_or_test()


def _client_host(request: Request) -> str | None:
    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return str(client.host)
    return None


def client_id(request: Request) -> str:
    return _client_host(request) or "unknown"


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def rate_limit_key(*parts: str) -> str:
    return ":".join(part for part in parts if part)


__all__ = [
    "DEFAULT_RATE_LIMIT_DETAIL",
    "RateLimitRule",
    "rate_limit_enabled",
    "client_id",
    "hash_value",
    "rate_limit_key",
]
