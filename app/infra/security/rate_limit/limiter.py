from __future__ import annotations

import asyncio
import math
import time
from contextlib import asynccontextmanager

from fastapi import HTTPException, status

from .rules import DEFAULT_RATE_LIMIT_DETAIL, RateLimitRule


class RateLimiter:
    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}
        self._last_seen: dict[str, float] = {}
        self._in_flight: dict[str, int] = {}
        self._in_flight_lock = asyncio.Lock()

    def reset(self) -> None:
        self._store.clear()
        self._last_seen.clear()
        self._in_flight.clear()

    def allow(self, key: str, rule: RateLimitRule) -> None:
        now = time.monotonic()
        entries = [
            t for t in self._store.get(key, []) if now - t <= rule.window_seconds
        ]
        if len(entries) >= rule.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=DEFAULT_RATE_LIMIT_DETAIL,
            )
        entries.append(now)
        self._store[key] = entries

    def throttle(self, key: str, min_interval_seconds: float) -> None:
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


__all__ = ["RateLimiter"]
