# app/main.py
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, candidate, health, simulations


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="SimuHire Backend", version="0.1.0")

    # --- Proxy / forwarded headers support (recommended behind Render) ---
    # Prefer running uvicorn with: --proxy-headers --forwarded-allow-ips="*"
    # This middleware is a safe extra layer if those flags are missed.
    try:
        from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    except Exception:
        # If the middleware isn't available for some reason, don't break startup.
        pass

    # --- CORS (helpful for local dev + direct calls; harmless with Vercel /api proxy) ---
    # Env-driven so you can configure per environment on Render:
    # - CORS_ALLOW_ORIGINS="https://frontend-five-zeta-84.vercel.app"
    # - CORS_ALLOW_ORIGIN_REGEX="https://.*\\.vercel\\.app"
    allow_origins = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS"))
    allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX")

    # Optional: support settings-based config if you later add it
    allow_origins = allow_origins or list(
        getattr(settings, "CORS_ALLOW_ORIGINS", []) or []
    )
    allow_origin_regex = allow_origin_regex or getattr(
        settings, "CORS_ALLOW_ORIGIN_REGEX", None
    )

    # If neither is set, keep a safe local-dev default.
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

    # --- Routers ---
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
