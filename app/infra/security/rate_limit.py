from __future__ import annotations

import asyncio
import hashlib
import math
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.infra.config import settings
from app.infra.env import is_local_or_test

DEFAULT_RATE_LIMIT_DETAIL = "Too many requests. Please slow down."


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: float


def rate_limit_enabled() -> bool:
    """Return True when rate limiting should be enforced."""
    if settings.RATE_LIMIT_ENABLED is not None:
        return bool(settings.RATE_LIMIT_ENABLED)
    return not is_local_or_test()


def client_id(request: Request) -> str:
    """Return a stable client identifier."""
    return _client_host(request) or "unknown"


def _client_host(request: Request) -> str | None:
    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return str(client.host)
    return None


def hash_value(value: str) -> str:
    """Return a stable hash for sensitive identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def rate_limit_key(*parts: str) -> str:
    """Build a consistent rate-limit key from parts."""
    return ":".join(part for part in parts if part)


class RateLimiter:
    """In-memory rate limiter for per-process throttling."""

    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}
        self._last_seen: dict[str, float] = {}
        self._in_flight: dict[str, int] = {}
        self._in_flight_lock = asyncio.Lock()

    def reset(self) -> None:
        """Clear in-memory rate limit state (tests/dev only)."""
        self._store.clear()
        self._last_seen.clear()
        self._in_flight.clear()

    def allow(self, key: str, rule: RateLimitRule) -> None:
        """Track usage for key and raise 429 when exceeded."""
        now = time.monotonic()
        entries = [t for t in self._store.get(key, []) if now - t <= rule.window_seconds]
        if len(entries) >= rule.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=DEFAULT_RATE_LIMIT_DETAIL,
            )
        entries.append(now)
        self._store[key] = entries

    def throttle(self, key: str, min_interval_seconds: float) -> None:
        """Enforce minimum time between requests for key."""
        now = time.monotonic()
        last = self._last_seen.get(key)
        if last is not None and now - last < min_interval_seconds:
            retry_after = max(1, int(math.ceil(min_interval_seconds - (now - last))))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=DEFAULT_RATE_LIMIT_DETAIL,
                headers={"Retry-After": str(retry_after)},
            )
        self._last_seen[key] = now

    @asynccontextmanager
    async def concurrency_guard(self, key: str, max_in_flight: int):
        """Limit concurrent operations for a key."""
        async with self._in_flight_lock:
            current = self._in_flight.get(key, 0)
            if current >= max_in_flight:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=DEFAULT_RATE_LIMIT_DETAIL,
                )
            self._in_flight[key] = current + 1
        try:
            yield
        finally:
            async with self._in_flight_lock:
                remaining = self._in_flight.get(key, 1) - 1
                if remaining <= 0:
                    self._in_flight.pop(key, None)
                else:
                    self._in_flight[key] = remaining


limiter = RateLimiter()
