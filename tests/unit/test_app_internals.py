import pytest

from app.core import db
from app.core.settings import settings
from app.main import _env_name, _parse_csv, create_app


class DummySession:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *exc):
        self.exited = True


class DummySessionMaker:
    def __init__(self) -> None:
        self.session = DummySession()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        await self.session.__aexit__(*exc)


@pytest.mark.asyncio
async def test_get_session_uses_async_session_maker(monkeypatch):
    maker = DummySessionMaker()
    monkeypatch.setattr(db, "async_session_maker", maker)

    gen = db.get_session()
    session = await gen.__anext__()
    assert session is maker.session
    await gen.aclose()
    assert maker.session.exited is True


def test_auth0_jwks_url_override(monkeypatch):
    monkeypatch.setattr(settings, "AUTH0_JWKS_URL", "https://example.com/jwks.json")
    assert settings.auth0_jwks_url == "https://example.com/jwks.json"


def test_parse_csv_and_env_name(monkeypatch):
    assert _parse_csv(None) == []
    assert _parse_csv(" a, b , ,") == ["a", "b"]
    monkeypatch.setattr(settings, "ENV", "Staging")
    monkeypatch.setenv("ENV", "prod")
    assert _env_name() == "staging"


def test_create_app_guard(monkeypatch):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(settings, "ENV", "prod")
    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_adds_proxy_headers(monkeypatch):
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", ["127.0.0.1/32"])
    calls: list[str] = []

    from fastapi import FastAPI

    original_add = FastAPI.add_middleware

    def record(self, middleware, *args, **kwargs):
        calls.append(getattr(middleware, "__name__", str(middleware)))
        return original_add(self, middleware, *args, **kwargs)

    monkeypatch.setattr(FastAPI, "add_middleware", record)

    create_app()
    assert "TrustedProxyHeadersMiddleware" in calls
    assert "ProxyHeadersMiddleware" not in calls


def test_create_app_skips_proxy_headers_without_trusted_cidrs(monkeypatch):
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", [])
    calls: list[str] = []

    from fastapi import FastAPI

    original_add = FastAPI.add_middleware

    def record(self, middleware, *args, **kwargs):
        calls.append(getattr(middleware, "__name__", str(middleware)))
        return original_add(self, middleware, *args, **kwargs)

    monkeypatch.setattr(FastAPI, "add_middleware", record)

    create_app()
    assert "TrustedProxyHeadersMiddleware" not in calls
    assert "ProxyHeadersMiddleware" not in calls


@pytest.mark.asyncio
async def test_lifespan_calls_init_db(monkeypatch):
    from app.api import main as api_main

    called = False

    async def fake_init():
        nonlocal called
        called = True

    monkeypatch.setattr(api_main, "init_db_if_needed", fake_init)
    async with api_main.lifespan(create_app()):
        pass
    assert called is True
