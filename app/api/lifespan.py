from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import init_db_if_needed as _init_db_if_needed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan handler to run startup/shutdown tasks."""
    from app.api import main as api_main  # late import to aid monkeypatch in tests

    await getattr(api_main, "init_db_if_needed", _init_db_if_needed)()
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


__all__ = ["lifespan"]
