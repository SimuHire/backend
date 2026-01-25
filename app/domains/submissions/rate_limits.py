from __future__ import annotations

from contextlib import asynccontextmanager

from app.infra.security import rate_limit

_DEFAULT_RATE_LIMIT_RULES = {
    "init": rate_limit.RateLimitRule(limit=20, window_seconds=30.0),
    "run": rate_limit.RateLimitRule(limit=20, window_seconds=30.0),
    "poll": rate_limit.RateLimitRule(limit=15, window_seconds=30.0),
    "submit": rate_limit.RateLimitRule(limit=10, window_seconds=30.0),
}

POLL_MIN_INTERVAL_SECONDS = 2.0
RUN_CONCURRENCY_LIMIT = 1


def _rules() -> dict[str, rate_limit.RateLimitRule]:
    try:
        from app.api.routes import tasks_codespaces

        override = getattr(tasks_codespaces, "_RATE_LIMIT_RULE", None)
        if isinstance(override, dict):
            return override
    except Exception:
        pass
    return _DEFAULT_RATE_LIMIT_RULES


def _rule_for(action: str) -> rate_limit.RateLimitRule:
    return _rules().get(action, rate_limit.RateLimitRule(limit=5, window_seconds=30.0))


def apply_rate_limit(candidate_session_id: int, action: str) -> None:
    if not rate_limit.rate_limit_enabled():
        return
    key = rate_limit.rate_limit_key("tasks", str(candidate_session_id), action)
    rate_limit.limiter.allow(key, _rule_for(action))


def throttle_poll(candidate_session_id: int, run_id: int) -> None:
    if not rate_limit.rate_limit_enabled():
        return
    rate_limit.limiter.throttle(
        rate_limit.rate_limit_key(
            "tasks", str(candidate_session_id), "poll", str(run_id)
        ),
        POLL_MIN_INTERVAL_SECONDS,
    )


@asynccontextmanager
async def concurrency_guard(candidate_session_id: int, action: str):
    if not rate_limit.rate_limit_enabled():
        yield
        return
    key = rate_limit.rate_limit_key("tasks", str(candidate_session_id), action)
    async with rate_limit.limiter.concurrency_guard(key, RUN_CONCURRENCY_LIMIT):
        yield
