from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class PerfStats:
    """Lightweight per-request DB stats."""

    db_count: int = 0
    db_time_ms: float = 0.0


def start_request_stats(perf_ctx: ContextVar) -> Token:
    """Initialize per-request stats in the provided ContextVar."""
    return perf_ctx.set(PerfStats())


def get_request_stats(perf_ctx: ContextVar) -> PerfStats:
    """Fetch current per-request stats (returns an empty instance by default)."""
    stats = perf_ctx.get()
    if stats is None:
        return PerfStats()
    return stats


def clear_request_stats(perf_ctx: ContextVar, token: Token) -> None:
    """Clear request stats ContextVar, ignoring reset errors."""
    try:
        perf_ctx.reset(token)
    except Exception:
        perf_ctx.set(None)


__all__ = [
    "PerfStats",
    "start_request_stats",
    "get_request_stats",
    "clear_request_stats",
]
