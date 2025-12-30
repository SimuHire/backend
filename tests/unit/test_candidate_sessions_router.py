from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import candidate_sessions


class StubSession:
    def __init__(self):
        self.committed = False
        self.refreshed = False

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj, **_kwargs):
        self.refreshed = True


@pytest.mark.asyncio
async def test_resolve_candidate_session_requires_verification(monkeypatch):
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
    with pytest.raises(HTTPException) as excinfo:
        await candidate_sessions.resolve_candidate_session(token="t" * 24, db=stub_db)
    assert excinfo.value.status_code == 401


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


@pytest.mark.asyncio
async def test_verify_candidate_session_returns_token(monkeypatch):
    stub_db = StubSession()
    expires_at = datetime.now(UTC)
    cs = SimpleNamespace(
        id=3,
        status="in_progress",
        completed_at=None,
        started_at=expires_at,
        candidate_name="Jane",
        access_token="access",
        access_token_expires_at=expires_at,
        simulation=SimpleNamespace(id=10, title="Sim", role="Backend"),
    )

    async def _verify(db, token, email, now):
        assert token == "t" * 24
        assert email == "test@example.com"
        assert isinstance(now, datetime)
        return cs

    monkeypatch.setattr(
        candidate_sessions.cs_service, "verify_email_and_issue_token", _verify
    )

    resp = await candidate_sessions.verify_candidate_session(
        token="t" * 24, payload=SimpleNamespace(email="test@example.com"), db=stub_db
    )

    assert resp.candidateToken == cs.access_token
    assert resp.tokenExpiresAt == expires_at
    assert resp.candidateName == cs.candidate_name
