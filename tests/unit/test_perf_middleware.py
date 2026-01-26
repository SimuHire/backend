import logging
import re
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import perf


def test_request_id_from_scope_handles_invalid_bytes(monkeypatch):
    # Invalid header bytes should fall back to a generated UUID instead of crashing.
    scope = {"headers": [(b"x-request-id", b"\xff")]}
    request_id = perf._request_id_from_scope(scope)
    assert request_id != "\xff"
    assert re.fullmatch(r"[a-f0-9-]{36}", request_id)


@pytest.mark.asyncio
async def test_perf_middleware_injects_request_id_and_logs(caplog, monkeypatch):
    monkeypatch.setattr(perf.settings, "DEBUG_PERF", True)
    caplog.set_level(logging.INFO, logger="app.core.perf")

    app = FastAPI()

    @app.get("/ping")
    async def _ping():
        return {"ok": True}

    app.add_middleware(perf.RequestPerfMiddleware)

    transport = ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ping", headers={"X-Request-Id": "keep-me"})

    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "keep-me"

    record = next(r for r in caplog.records if r.message == "perf_request")
    assert record.request_id == "keep-me"
    assert record.db_count == 0
    # Context var should be cleared after request.
    assert perf._perf_ctx.get() is None
    monkeypatch.setattr(perf.settings, "DEBUG_PERF", False)


@pytest.mark.asyncio
async def test_perf_middleware_noop_when_debug_disabled(monkeypatch):
    monkeypatch.setattr(perf.settings, "DEBUG_PERF", False)
    app = FastAPI()

    @app.get("/ping")
    async def _ping():
        return {"ok": True}

    app.add_middleware(perf.RequestPerfMiddleware)

    transport = ASGITransport(app=app, client=("10.0.0.1", 9999))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ping", headers={"X-Request-Id": "noop"})

    assert resp.status_code == 200
    assert "x-request-id" not in resp.headers


@pytest.mark.asyncio
async def test_attach_sqlalchemy_listeners_guard(monkeypatch):
    monkeypatch.setattr(perf, "_listeners_attached", False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        perf.attach_sqlalchemy_listeners(engine)
        assert perf._listeners_attached is True
        # Subsequent calls should be no-ops and not raise.
        perf.attach_sqlalchemy_listeners(engine)
    finally:
        await engine.dispose()
    # Reset for other tests that may rely on defaults.
    perf._listeners_attached = False


def test_clear_request_stats_error_path(monkeypatch):
    class BrokenCtx:
        def reset(self, token):
            raise RuntimeError("boom")

        def set(self, value):
            self.value = value
            return value

    token = perf._start_request_stats()
    monkeypatch.setattr(perf, "_perf_ctx", BrokenCtx())
    perf._clear_request_stats(token)


def test_get_request_stats_returns_default(monkeypatch):
    monkeypatch.setattr(
        perf, "_perf_ctx", perf.ContextVar("perf_ctx_test", default=None)
    )
    stats = perf._get_request_stats()
    assert stats.db_count == 0 and stats.db_time_ms == 0


@pytest.mark.asyncio
async def test_sqlalchemy_listeners_record_stats(monkeypatch):
    monkeypatch.setattr(perf.settings, "DEBUG_PERF", True)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    perf.attach_sqlalchemy_listeners(engine)
    token = perf._start_request_stats()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        stats = perf._get_request_stats()
        assert stats.db_count >= 1
        assert stats.db_time_ms >= 0
    finally:
        perf._clear_request_stats(token)
        await engine.dispose()
    monkeypatch.setattr(perf.settings, "DEBUG_PERF", False)


def test_sqlalchemy_listeners_early_return_paths(monkeypatch):
    captured = {}

    def fake_listens_for(_target, name):
        def decorator(fn):
            captured[name] = fn
            return fn

        return decorator

    monkeypatch.setattr(perf, "_listeners_attached", False)
    monkeypatch.setattr(perf, "event", SimpleNamespace(listens_for=fake_listens_for))
    dummy_engine = SimpleNamespace(sync_engine=object())
    perf.attach_sqlalchemy_listeners(dummy_engine)

    ctx = SimpleNamespace()
    monkeypatch.setattr(perf, "perf_logging_enabled", lambda: False)
    captured["before_cursor_execute"](None, None, None, None, ctx, None)
    captured["after_cursor_execute"](None, None, None, None, ctx, None)

    monkeypatch.setattr(perf, "perf_logging_enabled", lambda: True)
    ctx_no_start = SimpleNamespace()
    captured["after_cursor_execute"](None, None, None, None, ctx_no_start, None)

    class DummyPerfCtx:
        def get(self):
            return None

    monkeypatch.setattr(perf, "_perf_ctx", DummyPerfCtx())
    ctx_start = SimpleNamespace(_tenon_perf_start=time.perf_counter())
    captured["after_cursor_execute"](None, None, None, None, ctx_start, None)
