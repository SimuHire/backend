import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.infra.config import settings
from app.infra.security import auth0, principal


def test_extract_principal_missing_email_claim():
    claims = {"sub": "auth0|123", "permissions": ["candidate:access"]}
    with pytest.raises(HTTPException) as excinfo:
        principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert excinfo.value.status_code == 401
    assert "Invalid token" in excinfo.value.detail


def test_extract_principal_missing_email_claim_config(monkeypatch):
    claims = {"sub": "auth0|123", "permissions": ["candidate:access"]}
    monkeypatch.setattr(settings.auth, "AUTH0_EMAIL_CLAIM", "")
    with pytest.raises(HTTPException) as excinfo:
        principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert excinfo.value.status_code == 500
    assert "AUTH0_EMAIL_CLAIM not configured" in excinfo.value.detail


def test_permissions_from_namespaced_claim(monkeypatch):
    monkeypatch.setattr(settings.auth, "AUTH0_EMAIL_CLAIM", "https://tenon.ai/email")
    monkeypatch.setattr(
        settings.auth, "AUTH0_PERMISSIONS_CLAIM", "https://tenon.ai/permissions"
    )
    claims = {
        "sub": "auth0|abc",
        "https://tenon.ai/email": "jane@example.com",
        "https://tenon.ai/permissions": ["candidate:access"],
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert "candidate:access" in p.permissions


def test_permissions_from_namespaced_string_claim(monkeypatch):
    monkeypatch.setattr(settings.auth, "AUTH0_EMAIL_CLAIM", "https://tenon.ai/email")
    claims = {
        "sub": "auth0|abc",
        "https://tenon.ai/email": "jane@example.com",
        "https://tenon.ai/permissions_str": "candidate:access recruiter:access",
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert "candidate:access" in p.permissions
    assert "recruiter:access" in p.permissions


def test_permissions_from_roles_mapping(monkeypatch):
    monkeypatch.setattr(settings.auth, "AUTH0_EMAIL_CLAIM", "https://tenon.ai/email")
    monkeypatch.setattr(settings.auth, "AUTH0_ROLES_CLAIM", "https://tenon.ai/roles")
    claims = {
        "sub": "auth0|abc",
        "https://tenon.ai/email": "recruiter@example.com",
        "https://tenon.ai/roles": ["senior-recruiter"],
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert "recruiter:access" in p.permissions


def test_extract_principal_supports_url_claim_keys(monkeypatch):
    monkeypatch.setattr(settings.auth, "AUTH0_EMAIL_CLAIM", "https://tenon.ai/email")
    monkeypatch.setattr(
        settings.auth, "AUTH0_PERMISSIONS_CLAIM", "https://tenon.ai/permissions"
    )
    claims = {
        "sub": "auth0|tenon123",
        "https://tenon.ai/email": "x@y.com",
        "https://tenon.ai/permissions": ["recruiter:access"],
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert p.email == "x@y.com"
    assert "recruiter:access" in p.permissions


@pytest.mark.asyncio
async def test_get_principal_auth0_error_does_not_crash(monkeypatch):
    def bad_decode(_token: str):
        raise auth0.Auth0Error("Invalid token")

    monkeypatch.setattr(auth0, "decode_auth0_token", bad_decode)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    request = Request({"type": "http", "headers": [(b"x-request-id", b"req-1")]})

    with pytest.raises(auth0.Auth0Error):
        await principal.get_principal(credentials, request)
