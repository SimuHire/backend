from __future__ import annotations

from fastapi import FastAPI

from app.api.routers import (
    admin_templates,
    auth,
    candidate_sessions,
    health,
    simulations,
    submissions,
    tasks_codespaces,
)
from app.core.settings import settings


def register_routers(app: FastAPI) -> None:
    prefix = settings.API_PREFIX
    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(admin_templates.router, prefix=f"{prefix}/admin", tags=["admin"])
    app.include_router(simulations.router, prefix=f"{prefix}", tags=["simulations"])
    app.include_router(
        candidate_sessions.router, prefix=f"{prefix}/candidate", tags=["candidate"]
    )
    app.include_router(
        tasks_codespaces.router, prefix=f"{prefix}/tasks", tags=["tasks"]
    )
    app.include_router(submissions.router, prefix=f"{prefix}")


__all__ = ["register_routers"]
