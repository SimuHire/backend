from __future__ import annotations

import logging
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.infra.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PerfStats:
    """Lightweight per-request DB stats."""

    db_count: int = 0
    db_time_ms: float = 0.0


_perf_ctx: ContextVar[PerfStats | None] = ContextVar("perf_ctx", default=None)
_listeners_attached = False


def perf_logging_enabled() -> bool:
    """Return True when perf debug logging is enabled."""
    return bool(getattr(settings, "DEBUG_PERF", False))


def _start_request_stats() -> Token[PerfStats | None]:
    return _perf_ctx.set(PerfStats())


def _get_request_stats() -> PerfStats:
    stats = _perf_ctx.get()
    if stats is None:
        return PerfStats()
    return stats


def _clear_request_stats(token: Token[PerfStats | None]) -> None:
    try:
        _perf_ctx.reset(token)
    except Exception:
        _perf_ctx.set(None)


def attach_sqlalchemy_listeners(engine: AsyncEngine) -> None:
    """Attach lightweight timing hooks for DB statements."""
    global _listeners_attached
    if _listeners_attached:
        return

    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ):
        if not perf_logging_enabled():
            return
        context._tenon_perf_start = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ):
        if not perf_logging_enabled():
            return
        start = getattr(context, "_tenon_perf_start", None)
        if start is None:
            return
        stats = _perf_ctx.get()
        if stats is None:
            return
        stats.db_count += 1
        stats.db_time_ms += (time.perf_counter() - start) * 1000

    _listeners_attached = True


class RequestPerfMiddleware(BaseHTTPMiddleware):
    """Middleware to log per-request timing + DB stats."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not perf_logging_enabled():
            return await call_next(request)

        started = time.perf_counter()
        token = _start_request_stats()
        status_code = 500
        response: Response | None = None

        try:
            response = await call_next(request)
            status_code = getattr(response, "status_code", status_code)
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            stats = _get_request_stats()
            route = request.scope.get("route")
            path_template = None
            if route is not None:
                path_template = getattr(route, "path", None) or getattr(
                    route, "path_format", None
                )
            path_template = path_template or request.url.path

            logger.info(
                "perf_request",
                extra={
                    "method": request.method,
                    "path_template": path_template,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                    "db_count": stats.db_count,
                    "db_time_ms": round(stats.db_time_ms, 3),
                },
            )
            _clear_request_stats(token)
