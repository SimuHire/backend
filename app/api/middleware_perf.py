from __future__ import annotations

from fastapi import FastAPI

from app.core.logging import configure_logging
from app.core.perf import RequestPerfMiddleware, perf_logging_enabled


def configure_core_logging() -> None:
    configure_logging()


def configure_perf_logging(app: FastAPI) -> None:
    if not perf_logging_enabled():
        return
    from app.core.db import engine
    from app.core.perf import attach_sqlalchemy_listeners

    attach_sqlalchemy_listeners(engine)
    app.add_middleware(RequestPerfMiddleware)


__all__ = ["configure_core_logging", "configure_perf_logging"]
