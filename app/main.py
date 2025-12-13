import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, candidate, health, simulations


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _env_name() -> str:
    return str(getattr(settings, "ENV", os.getenv("ENV", "local"))).lower()


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    if os.getenv("DEV_AUTH_BYPASS") == "1" and _env_name() != "local":
        raise RuntimeError(
            "Refusing to start: DEV_AUTH_BYPASS enabled outside ENV=local"
        )

    app = FastAPI(title="SimuHire Backend", version="0.1.0")

    try:
        from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    except Exception:
        pass

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])
    app.include_router(
        simulations.router,
        prefix=f"{settings.API_PREFIX}/simulations",
        tags=["simulations"],
    )
    app.include_router(
        candidate.router,
        prefix=f"{settings.API_PREFIX}/candidate",
        tags=["candidate"],
    )

    return app


app = create_app()
