import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


@pytest_asyncio.fixture
async def async_session():
    ASYNC_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(ASYNC_URL, echo=False)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE companies, users, simulations, tasks, candidate_sessions, submissions RESTART IDENTITY CASCADE"
            )
        )

    SessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with SessionLocal() as session:
        yield session

    await engine.dispose()
