import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.infra import proxy_headers
from app.infra.proxy_headers import TrustedProxyHeadersMiddleware


def _proxy_test_app(trusted_proxy_cidrs: list[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/ip")
    async def ip(request: Request):
        return {"host": request.client.host}

    app.add_middleware(
        TrustedProxyHeadersMiddleware, trusted_proxy_cidrs=trusted_proxy_cidrs
    )
    return app


@pytest.mark.asyncio
async def test_trusted_proxy_uses_x_forwarded_for():
    app = _proxy_test_app(["127.0.0.1/32"])
    transport = ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ip", headers={"X-Forwarded-For": "203.0.113.5"})
    assert resp.json()["host"] == "203.0.113.5"


@pytest.mark.asyncio
async def test_untrusted_proxy_ignores_x_forwarded_for():
    app = _proxy_test_app(["10.0.0.0/8"])
    transport = ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ip", headers={"X-Forwarded-For": "203.0.113.5"})
    assert resp.json()["host"] == "127.0.0.1"


def test_proxy_header_helper_validation():
    assert proxy_headers._is_valid_ip("invalid") is False
    assert proxy_headers._is_valid_cidr("bad") is False
    assert proxy_headers._ip_in_trusted("127.0.0.1", []) is False
    assert proxy_headers._ip_in_trusted("not-an-ip", []) is False


@pytest.mark.asyncio
async def test_proxy_headers_no_client_and_non_http(monkeypatch):
    class DummyApp:
        def __init__(self):
            self.calls = 0

        async def __call__(self, scope, receive, send):
            self.calls += 1

    middleware = TrustedProxyHeadersMiddleware(
        DummyApp(), trusted_proxy_cidrs=["127.0.0.1/32"]
    )
    # Non-HTTP scope should bypass header handling
    await middleware({"type": "websocket"}, lambda: None, lambda msg: msg)
    # Missing client should also bypass without errors
    await middleware({"type": "http", "headers": []}, lambda: None, lambda msg: msg)
