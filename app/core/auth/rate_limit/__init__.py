from __future__ import annotations

from app.core.settings import settings

from .limiter import RateLimiter
from .rules import (
    DEFAULT_RATE_LIMIT_DETAIL,
    RateLimitRule,
    client_id,
    hash_value,
    rate_limit_enabled,
    rate_limit_key,
)

limiter = RateLimiter()

__all__ = [
    "DEFAULT_RATE_LIMIT_DETAIL",
    "RateLimitRule",
    "RateLimiter",
    "rate_limit_enabled",
    "client_id",
    "hash_value",
    "rate_limit_key",
    "limiter",
    "settings",
]
