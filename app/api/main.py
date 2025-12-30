import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    candidate_sessions,
    health,
    simulations,
    submissions,
    tasks_codespaces,
)
from app.infra.config import settings
from app.infra.db import init_db_if_needed
from app.infra.env import env_name


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
    yield


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    if os.getenv("DEV_AUTH_BYPASS") == "1" and _env_name() != "local":
        raise RuntimeError(
            "Refusing to start: DEV_AUTH_BYPASS enabled outside ENV=local"
        )

    app = FastAPI(title="SimuHire Backend", version="0.1.0", lifespan=lifespan)

    _configure_proxy_headers(app)
    _configure_cors(app)
    _register_routers(app)

    return app


def _configure_proxy_headers(app: FastAPI) -> None:
    """Add proxy headers middleware if available (e.g., behind a load balancer)."""
    try:
        from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    except Exception:
        # Optional dependency; skip if unavailable.
        pass


def _cors_config() -> tuple[list[str], str | None]:
    """Build CORS origins and regex from env/settings with sensible defaults."""
    allow_origins = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS"))
    allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX")

    allow_origins = allow_origins or list(
        getattr(settings, "CORS_ALLOW_ORIGINS", []) or []
    )
    allow_origin_regex = allow_origin_regex or getattr(
        settings, "CORS_ALLOW_ORIGIN_REGEX", None
    )

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


def _register_routers(app: FastAPI) -> None:
    prefix = settings.API_PREFIX
    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["auth"])
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
