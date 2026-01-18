from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.config import settings
from app.infra.db.base import Base
from app.infra.perf import attach_sqlalchemy_listeners

DEFAULT_SQLITE_URL: Final[
    str
] = f"sqlite+aiosqlite:///{Path(__file__).resolve().parents[3] / 'local.db'}"
USING_SQLITE_FALLBACK = False


def _create_engine():
    global USING_SQLITE_FALLBACK
    try:
        db_url = settings.database.async_url
    except ValueError:
        db_url = DEFAULT_SQLITE_URL
        USING_SQLITE_FALLBACK = True

    return create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        future=True,
    )


engine = _create_engine()
attach_sqlalchemy_listeners(engine)

async_session_maker = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

AsyncSessionLocal = async_session_maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a scoped async database session."""
    async with async_session_maker() as session:
        yield session


async def init_db_if_needed() -> None:
    """Create tables when using the sqlite fallback."""
    if not USING_SQLITE_FALLBACK:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
