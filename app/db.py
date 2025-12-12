# app/db.py
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

engine = create_async_engine(
    settings.database_url_async,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

AsyncSessionLocal = async_session_maker

Base = declarative_base()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a scoped async database session."""
    async with async_session_maker() as session:
        yield session
