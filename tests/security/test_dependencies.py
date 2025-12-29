from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import dependencies
from tests.factories import create_recruiter


def _make_request(headers: dict[str, str], host: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 1234),
        "path": "/",
        "method": "GET",
        "query_string": b"",
        "server": ("test", 80),
    }

    async def _receive():
        return {"type": "http.request"}

    return Request(scope, _receive)


@pytest.mark.asyncio
async def test_dev_bypass_allows_local_requests(async_session, monkeypatch):
    user = await create_recruiter(async_session, email="dev@local.test")
    req = _make_request({"x-dev-user-email": user.email})
    monkeypatch.setattr(dependencies, "_env_name", lambda: "local")
    result = await dependencies._dev_bypass_user(req, async_session)
    assert result.email == user.email


@pytest.mark.asyncio
async def test_dev_bypass_rejects_non_localhost(async_session, monkeypatch):
    user = await create_recruiter(async_session, email="remote@local.test")
    req = _make_request({"x-dev-user-email": user.email}, host="10.0.0.1")
    monkeypatch.setattr(dependencies, "_env_name", lambda: "local")
    with pytest.raises(Exception) as excinfo:
        await dependencies._dev_bypass_user(req, async_session)
    assert "localhost" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_dev_bypass_guard_against_prod(monkeypatch):
    req = _make_request({"x-dev-user-email": "x@example.com"})
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(dependencies, "_env_name", lambda: "prod")
    with pytest.raises(RuntimeError):
        await dependencies._dev_bypass_user(req, None)


@pytest.mark.asyncio
async def test_auth0_user_creates_new_user(async_session, monkeypatch):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    monkeypatch.setattr(
        dependencies.auth0,
        "decode_auth0_token",
        lambda _t: {"email": "newuser@example.com", "name": "New User"},
    )

    user = await dependencies._auth0_user(creds, async_session)
    assert user.email == "newuser@example.com"
    assert user.role == "recruiter"


def test_env_name_override(monkeypatch):
    override_module = type("m", (), {"_env_name": lambda: "override"})
    monkeypatch.setitem(
        dependencies.sys.modules, "app.core.security.current_user", override_module
    )
    assert dependencies._env_name() == "override"


@pytest.mark.asyncio
async def test_dev_bypass_returns_none_when_header_missing(monkeypatch):
    req = _make_request({})
    monkeypatch.setattr(dependencies, "_env_name", lambda: "local")
    assert await dependencies._dev_bypass_user(req, None) is None


@pytest.mark.asyncio
async def test_dev_bypass_fallback_session_maker(monkeypatch):
    req = _make_request({"x-dev-user-email": "missing@example.com"})
    monkeypatch.setattr(dependencies, "_env_name", lambda: "local")

    class DummySession:
        async def execute(self, *_a, **_k):
            class R:
                def scalar_one_or_none(self):
                    return None

            return R()

        async def commit(self):
            return None

    @asynccontextmanager
    async def dummy_maker():
        yield DummySession()

    monkeypatch.setitem(
        dependencies.sys.modules,
        "app.core.security.current_user",
        type("mod", (), {"async_session_maker": dummy_maker}),
    )

    with pytest.raises(Exception) as excinfo:
        await dependencies._dev_bypass_user(req, None)
    assert "Dev user not found" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_auth0_user_uses_fallback_session(monkeypatch):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    monkeypatch.setattr(
        dependencies.auth0,
        "decode_auth0_token",
        lambda _t: {"email": "fallback@example.com"},
    )

    class DummySession:
        def __init__(self):
            self.added = False
            self.committed = False
            self.refreshed = False

        async def execute(self, *_a, **_k):
            class R:
                def scalar_one_or_none(self_inner):
                    return None

            return R()

        def add(self, _obj):
            self.added = True

        async def commit(self):
            self.committed = True

        async def refresh(self, _obj):
            self.refreshed = True

    @asynccontextmanager
    async def dummy_maker():
        yield DummySession()

    monkeypatch.setitem(
        dependencies.sys.modules,
        "app.core.security.current_user",
        type("mod", (), {"async_session_maker": dummy_maker}),
    )

    user = await dependencies._auth0_user(creds, None)
    assert user.email == "fallback@example.com"
    assert user.role == "recruiter"


@pytest.mark.asyncio
async def test_auth0_user_handles_integrity_error(monkeypatch):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    monkeypatch.setattr(
        dependencies.auth0,
        "decode_auth0_token",
        lambda _t: {"email": "dup@example.com"},
    )

    class DummySession:
        def __init__(self):
            self.rollback_called = False
            self.calls = 0

        async def execute(self, *_a, **_k):
            self.calls += 1

            class R:
                def scalar_one_or_none(self_inner):
                    if self.calls == 1:
                        return None
                    return type("User", (), {"email": "dup@example.com"})

            return R()

        def add(self, _obj):
            return None

        async def commit(self):
            raise dependencies.IntegrityError("", {}, None)

        async def rollback(self):
            self.rollback_called = True

    session = DummySession()
    user = await dependencies._auth0_user(creds, session)
    assert user.email == "dup@example.com"
    assert session.rollback_called is True


@pytest.mark.asyncio
async def test_get_current_user_prefers_dev_bypass(monkeypatch, async_session):
    req = _make_request({"x-dev-user-email": "dev@local.test"})
    dummy_user = object()

    async def _return_user(*_a, **_k):
        return dummy_user

    monkeypatch.setattr(dependencies, "_dev_bypass_user", _return_user)
    result = await dependencies.get_current_user(req, None, async_session)
    assert result is dummy_user


def test_env_helpers(monkeypatch):
    monkeypatch.setattr(dependencies.settings, "ENV", "Prod")
    assert dependencies._env_name_base() == "prod"
    # No override module present -> falls back to base env
    dependencies.sys.modules.pop("app.core.security.current_user", None)
    assert dependencies._env_name() == "prod"


@pytest.mark.asyncio
async def test_dev_bypass_returns_none_for_prod_env(monkeypatch):
    req = _make_request({"x-dev-user-email": "prod@local.test"})
    monkeypatch.setattr(dependencies, "_env_name", lambda: "prod")
    assert await dependencies._dev_bypass_user(req, None) is None
