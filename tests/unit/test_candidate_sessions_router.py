from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routes.candidate import sessions as candidate_sessions


class StubSession:
    def __init__(self):
        self.committed = False
        self.refreshed = False

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        self.refreshed = True


@pytest.mark.asyncio
async def test_resolve_candidate_session_sets_started(monkeypatch):
    stub_db = StubSession()
    cs = SimpleNamespace(
        id=1,
        status="not_started",
        started_at=None,
        completed_at=None,
        candidate_name="Jane",
        simulation=SimpleNamespace(id=10, title="Sim", role="Backend"),
    )

    async def _return_cs(*_a, **_k):
        return cs

    monkeypatch.setattr(candidate_sessions.cs_service, "fetch_by_token", _return_cs)
    result = await candidate_sessions.resolve_candidate_session(
        token="t" * 24, db=stub_db
    )
    assert stub_db.committed is True
    assert stub_db.refreshed is True
    assert result.status == "in_progress"
    assert cs.started_at is not None
    assert isinstance(result.startedAt, datetime)
    assert cs.started_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_get_current_task_marks_completed(monkeypatch):
    stub_db = StubSession()
    cs = SimpleNamespace(
        id=2,
        status="in_progress",
        completed_at=None,
        simulation_id=1,
    )
    current_task = SimpleNamespace(
        id=99, day_index=3, title="Task", type="code", description="desc"
    )

    async def _fetch_by_id(db, session_id, token, now):
        assert session_id == cs.id
        return cs

    async def _progress_snapshot(db, candidate_session):
        return (
            [current_task],
            {1, 2, 3},
            current_task,
            3,
            3,
            True,
        )

    monkeypatch.setattr(
        candidate_sessions.cs_service, "fetch_by_id_and_token", _fetch_by_id
    )
    monkeypatch.setattr(
        candidate_sessions.cs_service, "progress_snapshot", _progress_snapshot
    )

    resp = await candidate_sessions.get_current_task(
        candidate_session_id=cs.id, x_candidate_token="tok", db=stub_db
    )
    assert resp.isComplete is True
    assert resp.currentDayIndex is None
    assert cs.status == "completed"
    assert stub_db.committed is True
    assert cs.completed_at is not None
