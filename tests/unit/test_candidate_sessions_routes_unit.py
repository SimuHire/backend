from types import SimpleNamespace

import pytest
from fastapi import Request

from app.api.routers import candidate_sessions
from app.core.auth import rate_limit


def _fake_request(scope_overrides: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "path": "/",
        "method": "GET",
        "query_string": b"",
        "server": ("test", 80),
    }
    if scope_overrides:
        scope.update(scope_overrides)
    return Request(scope, lambda: None)


class _AllowLimiter:
    def __init__(self):
        self.calls: list[tuple] = []

    def allow(self, key, rule):
        self.calls.append((key, rule))


@pytest.mark.asyncio
async def test_candidate_session_rate_limits(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: True)
    limiter = _AllowLimiter()
    monkeypatch.setattr(rate_limit, "limiter", limiter)
    db = SimpleNamespace(
        commits=[],
        refreshed=[],
    )

    async def _noop_commit():
        db.commits.append("commit")

    async def _noop_refresh(obj):
        db.refreshed.append(obj)

    db.commit = _noop_commit
    db.refresh = _noop_refresh
    principal = SimpleNamespace(
        sub="sub",
        email="user@example.com",
        claims={},
        permissions=["candidate:access"],
    )
    cs_obj = SimpleNamespace(
        id=1,
        status="in_progress",
        started_at=None,
        completed_at=None,
        candidate_name="Name",
        simulation=SimpleNamespace(id=2, title="T", role="R"),
    )

    async def fake_claim(db, token, principal, now):
        return cs_obj

    async def fake_fetch(db, cs_id, principal, now):
        return cs_obj

    async def fake_progress(db, cs):
        return (
            [],
            set(),
            SimpleNamespace(
                id=9, day_index=1, title="Task", type="code", description=""
            ),
            0,
            1,
            True,
        )

    async def fake_invites(db, principal):
        return []

    monkeypatch.setattr(
        candidate_sessions.cs_service, "claim_invite_with_principal", fake_claim
    )
    monkeypatch.setattr(
        candidate_sessions.cs_service, "fetch_owned_session", fake_fetch
    )
    monkeypatch.setattr(
        candidate_sessions.cs_service, "progress_snapshot", fake_progress
    )
    monkeypatch.setattr(
        candidate_sessions.cs_service, "invite_list_for_principal", fake_invites
    )

    await candidate_sessions.resolve_candidate_session(
        token="x" * 20, request=_fake_request(), principal=principal, db=db
    )
    await candidate_sessions.claim_candidate_session(
        token="x" * 20, request=_fake_request(), db=db, principal=principal
    )
    await candidate_sessions.get_current_task(
        candidate_session_id=1, request=_fake_request(), principal=principal, db=db
    )
    await candidate_sessions.list_candidate_invites(
        request=_fake_request(), principal=principal, db=db
    )

    assert len(limiter.calls) == 4
