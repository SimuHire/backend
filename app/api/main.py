from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_utils import register_error_handlers
from app.api.routes import (
    admin_templates,
    auth,
    candidate_sessions,
    health,
    simulations,
    submissions,
    tasks_codespaces,
)
from app.core.brand import APP_NAME
from app.infra.config import settings
from app.infra.db import init_db_if_needed
from app.infra.env import env_name
from app.infra.logging import configure_logging
from app.infra.perf import RequestPerfMiddleware, perf_logging_enabled
from app.infra.proxy_headers import TrustedProxyHeadersMiddleware, trusted_proxy_cidrs
from app.infra.request_limits import RequestSizeLimitMiddleware


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _env_name() -> str:
    return env_name()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan handler to run startup/shutdown tasks."""
    await init_db_if_needed()
    try:
        yield
    finally:
        try:
            from app.api.dependencies.github_native import _github_client_singleton

            client = _github_client_singleton()
            await client.aclose()
        except Exception:
            # Best-effort cleanup; swallow errors to avoid blocking shutdown.
            pass


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    configure_logging()
    if settings.dev_auth_bypass_enabled and _env_name() != "local":
        raise RuntimeError(
            "Refusing to start: DEV_AUTH_BYPASS enabled outside ENV=local"
        )

    app = FastAPI(title=f"{APP_NAME} Backend", version="0.1.0", lifespan=lifespan)

    _configure_perf_logging(app)
    _configure_proxy_headers(app)
    _configure_request_limits(app)
    _configure_cors(app)
    _register_routers(app)
    register_error_handlers(app)

    return app


def _configure_proxy_headers(app: FastAPI) -> None:
    """Add proxy headers middleware when trusted proxies are configured."""
    cidrs = trusted_proxy_cidrs()
    if not cidrs:
        return
    app.add_middleware(TrustedProxyHeadersMiddleware, trusted_proxy_cidrs=cidrs)


def _cors_config() -> tuple[list[str], str | None]:
    """Build CORS origins and regex from env/settings with sensible defaults."""
    origins_from_settings = getattr(settings, "cors", None)
    allow_origins = []
    allow_origin_regex = None
    if origins_from_settings:
        allow_origins = list(origins_from_settings.CORS_ALLOW_ORIGINS or [])
        allow_origin_regex = origins_from_settings.CORS_ALLOW_ORIGIN_REGEX

    if not allow_origins and not allow_origin_regex:
        allow_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    return allow_origins, allow_origin_regex


def _configure_cors(app: FastAPI) -> None:
    allow_origins, allow_origin_regex = _cors_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _configure_request_limits(app: FastAPI) -> None:
    """Add request size limits to guard against abuse."""
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
    )


def _configure_perf_logging(app: FastAPI) -> None:
    """Attach perf middleware when enabled."""
    if not perf_logging_enabled():
        return
    app.add_middleware(RequestPerfMiddleware)


def _register_routers(app: FastAPI) -> None:
    prefix = settings.API_PREFIX
    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(
        admin_templates.router,
        prefix=f"{prefix}/admin",
        tags=["admin"],
    )
    app.include_router(
        simulations.router,
        prefix=f"{prefix}/simulations",
        tags=["simulations"],
    )
    app.include_router(
        candidate_sessions.router,
        prefix=f"{prefix}/candidate",
        tags=["candidate"],
    )
    app.include_router(
        tasks_codespaces.router, prefix=f"{prefix}/tasks", tags=["tasks"]
    )
    app.include_router(
        submissions.router,
        prefix=f"{prefix}/submissions",
    )


app = create_app()
