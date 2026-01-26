import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routers import auth as auth_routes
from app.core.auth import auth0, current_user
from app.core.db import get_session
from app.core.settings import settings
from app.main import app


@pytest.mark.asyncio
async def test_auth_me_creates_and_returns_user(
    async_session, monkeypatch, override_dependencies
):
    """Auth endpoint should decode token and create user if missing."""

    def fake_decode_auth0_token(_token: str) -> dict[str, str]:
        return {
            "email": "recruiter@example.com",
            "name": "Recruiter One",
            "sub": "auth0|test",
            "permissions": ["recruiter:access"],
        }

    session_maker = async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )

    async def override_get_session():
        yield async_session

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode_auth0_token)
    monkeypatch.setattr(current_user, "async_session_maker", session_maker)
    with override_dependencies({get_session: override_get_session}):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer fake-token"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "recruiter@example.com"
    assert body["role"] == "recruiter"


@pytest.mark.asyncio
async def test_auth_me_rate_limited_in_prod(
    async_session, monkeypatch, override_dependencies
):
    def fake_decode_auth0_token(_token: str) -> dict[str, str]:
        return {
            "email": "recruiter@example.com",
            "name": "Recruiter One",
            "sub": "auth0|test",
            "permissions": ["recruiter:access"],
        }

    session_maker = async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )

    async def override_get_session():
        yield async_session

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode_auth0_token)
    monkeypatch.setattr(current_user, "async_session_maker", session_maker)
    monkeypatch.setattr(settings, "ENV", "prod")
    auth_routes.rate_limit.limiter.reset()
    original_rule = auth_routes.AUTH_ME_RATE_LIMIT
    auth_routes.AUTH_ME_RATE_LIMIT = auth_routes.rate_limit.RateLimitRule(
        limit=1, window_seconds=60.0
    )

    with override_dependencies({get_session: override_get_session}):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            first = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer fake-token"},
            )
            second = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer fake-token"},
            )

    assert first.status_code == 200, first.text
    assert second.status_code == 429

    auth_routes.AUTH_ME_RATE_LIMIT = original_rule
    auth_routes.rate_limit.limiter.reset()


@pytest.mark.asyncio
async def test_auth_logout_is_stateless(async_client):
    res = await async_client.post("/api/auth/logout")

    assert res.status_code == 204
    assert res.headers.get("cache-control") == "no-store"
    assert res.headers.get("pragma") == "no-cache"
    assert "set-cookie" not in res.headers
    assert res.headers.get("location") is None
