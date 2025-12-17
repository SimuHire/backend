import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db import get_session
from app.main import app
from app.models.user import User
from app.security.current_user import get_current_user


@pytest_asyncio.fixture
async def async_session():
    ASYNC_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(ASYNC_URL, echo=False)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE companies, users, simulations, tasks, candidate_sessions, submissions, execution_profiles "
                "RESTART IDENTITY CASCADE"
            )
        )

    SessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with SessionLocal() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession):
    async def override_get_session():
        yield async_session

    async def override_get_current_user(request: Request) -> User:
        # In tests, authenticate via x-dev-user-email using the SAME async_session
        email = (request.headers.get("x-dev-user-email") or "").strip()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing x-dev-user-email header",
            )

        result = await async_session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Dev user not found: {email}. Seed this user in the DB first.",
            )
        return user

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Optional: base_url can stay as-is now since we bypass localhost checks entirely.
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)
