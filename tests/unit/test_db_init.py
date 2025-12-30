from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.infra import db


@pytest.mark.asyncio
async def test_init_db_if_needed_runs_when_using_sqlite(monkeypatch):
    conn_called = False

    class StubConn:
        async def run_sync(self, fn):
            nonlocal conn_called
            conn_called = True
            return None

    @asynccontextmanager
    async def begin():
        yield StubConn()

    monkeypatch.setattr(db, "USING_SQLITE_FALLBACK", True)
    monkeypatch.setattr(db, "engine", SimpleNamespace(begin=begin))

    await db.init_db_if_needed()
    assert conn_called is True


@pytest.mark.asyncio
async def test_init_db_if_needed_noop_when_not_fallback(monkeypatch):
    monkeypatch.setattr(db, "USING_SQLITE_FALLBACK", False)
    called = False

    async def fake_begin():
        nonlocal called
        called = True
        yield None

    monkeypatch.setattr(db, "engine", SimpleNamespace(begin=fake_begin))
    await db.init_db_if_needed()
    assert called is False
