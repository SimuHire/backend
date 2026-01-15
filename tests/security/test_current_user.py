import pytest
from httpx import AsyncClient

from app.infra.db import get_session
from app.infra.security import auth0, current_user
from app.main import app


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
    assert res.headers["content-type"].startswith("application/json")
    assert res.headers.get("location") is None
    assert res.json()["detail"] == "Not authenticated"


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

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_expired_token_returns_json_401(async_session, monkeypatch):
    async def override_get_session():
        yield async_session

    def fake_decode(_token: str) -> dict:
        raise auth0.Auth0Error("Token expired")

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

    assert res.status_code == 401
    assert res.headers["content-type"].startswith("application/json")
    assert res.headers.get("location") is None
    assert res.json()["detail"] == "Token expired"
