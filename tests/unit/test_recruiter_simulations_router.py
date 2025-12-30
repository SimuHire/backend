from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routes import simulations as recruiter_sims


@pytest.mark.asyncio
async def test_create_candidate_invite_happy_path(monkeypatch):
    user = SimpleNamespace(id=1)
    cs = SimpleNamespace(id=2, token="tok")

    async def _require_owned(db, simulation_id, recruiter_id):
        assert recruiter_id == user.id
        return SimpleNamespace(id=simulation_id)

    async def _create_invite(db, simulation_id, payload, now):
        assert payload.candidateName == "Name"
        return cs

    monkeypatch.setattr(recruiter_sims, "ensure_recruiter_or_none", lambda _u: None)
    monkeypatch.setattr(
        recruiter_sims.sim_service, "require_owned_simulation", _require_owned
    )
    monkeypatch.setattr(recruiter_sims.sim_service, "create_invite", _create_invite)
    monkeypatch.setattr(
        recruiter_sims.sim_service,
        "invite_url",
        lambda token: f"https://portal/{token}",
    )

    payload = SimpleNamespace(candidateName="Name", inviteEmail="a@b.com")
    resp = await recruiter_sims.create_candidate_invite(
        simulation_id=5, payload=payload, db=None, user=user
    )
    assert resp.inviteUrl.endswith("/tok")
    assert resp.candidateSessionId == cs.id


@pytest.mark.asyncio
async def test_list_simulation_candidates_calls_service(monkeypatch):
    user = SimpleNamespace(id=7)
    cs = SimpleNamespace(
        id=11,
        invite_email="x@y.com",
        candidate_name="Jane",
        status="in_progress",
        started_at=datetime.now(UTC),
        completed_at=None,
    )
    rows = [(cs, None)]

    monkeypatch.setattr(recruiter_sims, "ensure_recruiter_or_none", lambda _u: None)

    async def _require_owned(*_a, **_k):
        return cs

    monkeypatch.setattr(
        recruiter_sims.sim_service,
        "require_owned_simulation",
        _require_owned,
    )

    async def _list_candidates(*_a, **_k):
        return rows

    monkeypatch.setattr(
        recruiter_sims.sim_service, "list_candidates_with_profile", _list_candidates
    )

    resp = await recruiter_sims.list_simulation_candidates(
        simulation_id=9, db=None, user=user
    )
    assert resp[0].candidateSessionId == cs.id
    assert resp[0].hasReport is False
