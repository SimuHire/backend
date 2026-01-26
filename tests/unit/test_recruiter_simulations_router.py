from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routers import simulations as recruiter_sims


def _request(host: str = "127.0.0.1"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=host))


@pytest.mark.asyncio
async def test_create_candidate_invite_happy_path(monkeypatch):
    user = SimpleNamespace(id=1)
    cs = SimpleNamespace(id=2, token="tok")
    task_day2 = SimpleNamespace(
        id=10, day_index=2, type="code", template_repo="org/template"
    )
    task_day3 = SimpleNamespace(
        id=11, day_index=3, type="debug", template_repo="org/template"
    )

    async def _require_owned_with_tasks(db, simulation_id, recruiter_id):
        assert recruiter_id == user.id
        return (
            SimpleNamespace(id=simulation_id, title="Sim", role="Engineer"),
            [task_day2, task_day3],
        )

    async def _create_or_resend_invite(db, simulation_id, payload, now):
        assert payload.candidateName == "Name"
        return cs, "created"

    async def _send_invite_email(*_args, **_kwargs):
        return SimpleNamespace(status="sent")

    async def _ensure_workspace(*_args, **_kwargs):
        return SimpleNamespace(id="ws")

    monkeypatch.setattr(recruiter_sims, "ensure_recruiter_or_none", lambda _u: None)
    monkeypatch.setattr(
        recruiter_sims.sim_service,
        "require_owned_simulation_with_tasks",
        _require_owned_with_tasks,
    )
    monkeypatch.setattr(
        recruiter_sims.sim_service, "create_or_resend_invite", _create_or_resend_invite
    )
    monkeypatch.setattr(
        recruiter_sims.notification_service, "send_invite_email", _send_invite_email
    )
    monkeypatch.setattr(
        recruiter_sims.submission_service, "ensure_workspace", _ensure_workspace
    )
    monkeypatch.setattr(
        recruiter_sims.sim_service,
        "invite_url",
        lambda token: f"https://portal/{token}",
    )
    email_service = SimpleNamespace(
        send_email=lambda **_k: SimpleNamespace(status="sent")
    )

    payload = SimpleNamespace(candidateName="Name", inviteEmail="a@b.com")
    resp = await recruiter_sims.create_candidate_invite(
        simulation_id=5,
        payload=payload,
        request=_request(),
        db=None,
        user=user,
        email_service=email_service,
        github_client=SimpleNamespace(),
    )
    assert resp.inviteUrl.endswith("/tok")
    assert resp.candidateSessionId == cs.id
    assert resp.outcome == "created"


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
    assert resp[0].hasFitProfile is False
