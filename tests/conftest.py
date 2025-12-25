from __future__ import annotations

import os

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models import Base, User
from app.security.current_user import get_current_user


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Ensure pytest-anyio uses asyncio for all async tests.
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Shared async engine for the test session (defaults to in-memory SQLite)."""
    test_url = os.getenv("TEST_DATABASE_URL") or "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(test_url, echo=False, pool_pre_ping=True, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Fresh database for each test."""
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(
        bind=db_engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )

    async with session_maker() as session:
        yield session
        # Roll back any open transaction so the connection returns cleanly.
        await session.rollback()


@pytest_asyncio.fixture(name="async_session")
async def _async_session_alias(db_session: AsyncSession) -> AsyncSession:
    """Backward-compatible alias for existing tests."""
    return db_session


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    """FastAPI TestClient wired to the shared async session + auth override."""

    async def override_get_session():
        yield db_session

    async def override_get_current_user(request: Request) -> User:
        email = (request.headers.get("x-dev-user-email") or "").strip()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing x-dev-user-email header",
            )

        result = await db_session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Dev user not found: {email}. Seed this user in the DB first.",
            )
        return user

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_header_factory():
    """Helper to build recruiter auth headers from a User."""

    def _build(user: User) -> dict[str, str]:
        return {"x-dev-user-email": user.email}

    return _build


@pytest.fixture
def candidate_header_factory():
    """Helper to build candidate headers from a session/token."""

    def _build(candidate_session_id: int, token: str) -> dict[str, str]:
        return {
            "x-candidate-token": token,
            "x-candidate-session-id": str(candidate_session_id),
        }

    return _build
