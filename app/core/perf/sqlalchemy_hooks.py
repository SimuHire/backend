from __future__ import annotations

import time

from sqlalchemy import event as sa_event


def register_listeners(engine, *, event_impl=sa_event, perf_ctx, perf_module):
    """Attach lightweight timing hooks for DB statements."""
    sync_engine = engine.sync_engine

    @event_impl.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        _conn, _cursor, _statement, _parameters, context, _executemany
    ):
        if not perf_module.perf_logging_enabled():
            return
        context._tenon_perf_start = time.perf_counter()

    @event_impl.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        _conn, _cursor, _statement, _parameters, context, _executemany
    ):
        if not perf_module.perf_logging_enabled():
            return
        start = getattr(context, "_tenon_perf_start", None)
        if start is None:
            return
        stats = perf_ctx.get()
        if stats is None:
            return
        stats.db_count += 1
        stats.db_time_ms += (time.perf_counter() - start) * 1000


__all__ = ["register_listeners", "sa_event"]
