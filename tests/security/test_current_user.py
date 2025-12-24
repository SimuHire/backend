import pytest
from httpx import AsyncClient

from app.db import get_session
from app.main import app
from app.security import auth0, current_user


@pytest.mark.asyncio
async def test_auth_me_requires_auth_header(async_session):
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides.pop(current_user.get_current_user, None)
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            res = await client.get("/api/auth/me")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_missing_email_claim(async_session, monkeypatch):
    async def override_get_session():
        yield async_session

    def fake_decode(_token: str) -> dict:
        return {}

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode)
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides.pop(current_user.get_current_user, None)

    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            res = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer token"},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 400
