from fastapi import FastAPI

from app.config import settings
from app.routers import auth, candidate, health, simulations


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="SimuHire Backend", version="0.1.0")

    # Routers
    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])
    app.include_router(
        simulations.router,
        prefix=f"{settings.API_PREFIX}/simulations",
        tags=["simulations"],
    )
    app.include_router(
        candidate.router, prefix=f"{settings.API_PREFIX}/candidate", tags=["candidate"]
    )

    return app


app = create_app()
