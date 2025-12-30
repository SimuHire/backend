import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infra.db import get_session
from app.infra.security import auth0, current_user
from app.main import app


@pytest.mark.asyncio
async def test_auth_me_creates_and_returns_user(
    async_session, monkeypatch, override_dependencies
):
    """Auth endpoint should decode token and create user if missing."""

    def fake_decode_auth0_token(_token: str) -> dict[str, str]:
        return {"email": "recruiter@example.com", "name": "Recruiter One"}

    session_maker = async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )

    async def override_get_session():
        yield async_session

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode_auth0_token)
    monkeypatch.setattr(current_user, "async_session_maker", session_maker)
    with override_dependencies({get_session: override_get_session}):
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer fake-token"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "recruiter@example.com"
    assert body["role"] == "recruiter"
