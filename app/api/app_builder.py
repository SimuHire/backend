from __future__ import annotations

from fastapi import FastAPI

from app.api.app_meta import _env_name
from app.api.errors.handlers import register_error_handlers
from app.api.lifespan import lifespan
from app.api.middleware import (
    configure_core_logging,
    configure_cors,
    configure_perf_logging,
    configure_proxy_headers,
    configure_request_limits,
)
from app.api.router_registry import register_routers
from app.core.brand import APP_NAME
from app.core.settings import settings


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    configure_core_logging()
    if settings.dev_auth_bypass_enabled and _env_name() != "local":
        raise RuntimeError(
            "Refusing to start: DEV_AUTH_BYPASS enabled outside ENV=local"
        )

    app = FastAPI(title=f"{APP_NAME} Backend", version="0.1.0", lifespan=lifespan)
    configure_perf_logging(app)
    configure_proxy_headers(app)
    configure_request_limits(app)
    configure_cors(app)
    register_routers(app)
    register_error_handlers(app)
    return app


__all__ = ["create_app"]
