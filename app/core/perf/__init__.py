from __future__ import annotations

import sys
from contextvars import ContextVar, Token

from sqlalchemy import event as sa_event

from app.core.settings import settings

from .config import perf_logging_enabled
from .context import (
    PerfStats,
    clear_request_stats,
    get_request_stats,
    start_request_stats,
)
from .middleware import _request_id_from_scope, create_request_perf_middleware
from .sqlalchemy_hooks import register_listeners

_perf_ctx: ContextVar[PerfStats | None] = ContextVar("perf_ctx", default=None)
_listeners_attached = False
event = sa_event


def _start_request_stats() -> Token[PerfStats | None]:
    return start_request_stats(_perf_ctx)


def _get_request_stats() -> PerfStats:
    return get_request_stats(_perf_ctx)


def _clear_request_stats(token: Token[PerfStats | None]) -> None:
    clear_request_stats(_perf_ctx, token)


def _get_perf_ctx():
    return _perf_ctx


RequestPerfMiddleware = create_request_perf_middleware(_get_perf_ctx)


def attach_sqlalchemy_listeners(engine) -> None:
    global _listeners_attached
    if _listeners_attached:
        return
    register_listeners(
        engine, event_impl=event, perf_ctx=_perf_ctx, perf_module=sys.modules[__name__]
    )
    _listeners_attached = True


__all__ = [
    "PerfStats",
    "RequestPerfMiddleware",
    "attach_sqlalchemy_listeners",
    "perf_logging_enabled",
    "_perf_ctx",
    "_start_request_stats",
    "_get_request_stats",
    "_clear_request_stats",
    "_request_id_from_scope",
    "_listeners_attached",
    "event",
    "settings",
]
