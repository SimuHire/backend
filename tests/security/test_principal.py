import pytest
from fastapi import HTTPException

from app.infra.config import settings
from app.infra.security import principal


def test_extract_principal_missing_email_claim():
    claims = {"sub": "auth0|123", "permissions": ["candidate:access"]}
    with pytest.raises(HTTPException) as excinfo:
        principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert excinfo.value.status_code == 400
    assert "Email claim missing" in excinfo.value.detail


def test_extract_principal_missing_email_claim_config(monkeypatch):
    claims = {"sub": "auth0|123", "permissions": ["candidate:access"]}
    monkeypatch.setattr(settings.auth, "AUTH0_EMAIL_CLAIM", "")
    with pytest.raises(HTTPException) as excinfo:
        principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert excinfo.value.status_code == 500
    assert "AUTH0_EMAIL_CLAIM not configured" in excinfo.value.detail


def test_permissions_from_namespaced_claim(monkeypatch):
    monkeypatch.setattr(
        settings.auth, "AUTH0_EMAIL_CLAIM", "https://simuhire.com/email"
    )
    claims = {
        "sub": "auth0|abc",
        "https://simuhire.com/email": "jane@example.com",
        "https://simuhire.com/permissions": ["candidate:access"],
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert "candidate:access" in p.permissions


def test_permissions_from_namespaced_string_claim(monkeypatch):
    monkeypatch.setattr(
        settings.auth, "AUTH0_EMAIL_CLAIM", "https://simuhire.com/email"
    )
    claims = {
        "sub": "auth0|abc",
        "https://simuhire.com/email": "jane@example.com",
        "https://simuhire.com/permissions_str": "candidate:access recruiter:access",
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert "candidate:access" in p.permissions
    assert "recruiter:access" in p.permissions


def test_permissions_from_roles_mapping(monkeypatch):
    monkeypatch.setattr(
        settings.auth, "AUTH0_EMAIL_CLAIM", "https://simuhire.com/email"
    )
    monkeypatch.setattr(
        settings.auth, "AUTH0_ROLES_CLAIM", "https://simuhire.com/roles"
    )
    claims = {
        "sub": "auth0|abc",
        "https://simuhire.com/email": "recruiter@example.com",
        "https://simuhire.com/roles": ["senior-recruiter"],
    }
    p = principal._extract_principal(claims)  # type: ignore[attr-defined]
    assert "recruiter:access" in p.permissions
