import pytest
from httpx import AsyncClient

from app.main import app
from app.security import auth0


@pytest.mark.anyio
async def test_auth_me_creates_and_returns_user(monkeypatch):
    def fake_decode_auth0_token(_token: str) -> dict[str, str]:
        return {"email": "recruiter@example.com", "name": "Recruiter One"}

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode_auth0_token)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "recruiter@example.com"
    assert body["role"] == "recruiter"
