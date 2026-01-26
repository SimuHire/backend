from __future__ import annotations

from contextlib import asynccontextmanager

from app.core.auth import rate_limit
from app.domains.candidate_sessions import service as cs_service
from app.domains.submissions.rate_limits import apply_rate_limit


def _rate_limit_or_429(candidate_session_id: int, action: str) -> None:
    """Enforce rate limit rules for a candidate action."""
    apply_rate_limit(candidate_session_id, action)


@asynccontextmanager
async def _concurrency_guard(key: str, limit: int):
    """Limit concurrent operations for a given key."""
    if not rate_limit.rate_limit_enabled():
        yield
        return
    async with rate_limit.limiter.concurrency_guard(key, limit):
        yield


async def _compute_current_task(db, cs):
    """Return current task for a candidate session."""
    tasks, _, current, *_ = await cs_service.progress_snapshot(db, cs)
    return current
