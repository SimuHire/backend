from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains import CandidateSession
from app.domains.simulations import service as sim_service
from tests.factories import create_recruiter, create_simulation


@pytest.mark.asyncio
async def test_require_owned_simulation_raises(monkeypatch):
    async def _return_none(*_a, **_k):
        return None

    monkeypatch.setattr(sim_service.sim_repo, "get_owned", _return_none, raising=False)
    with pytest.raises(Exception) as excinfo:
        await sim_service.require_owned_simulation(db=None, simulation_id=1, user_id=2)
    assert excinfo.value.status_code == 404


def test_template_repo_for_task_variants(monkeypatch):
    monkeypatch.setattr(sim_service.settings.github, "GITHUB_TEMPLATE_OWNER", "owner")
    monkeypatch.setattr(
        sim_service, "resolve_template_repo_full_name", lambda _key: "template-only"
    )
    repo = sim_service._template_repo_for_task(5, "code", "python-fastapi")
    assert repo == "template-only"
    # Day index 2 uses owner override when repo name lacks owner prefix
    repo_with_owner = sim_service._template_repo_for_task(2, "code", "python-fastapi")
    assert repo_with_owner.startswith("owner/")
    assert sim_service._template_repo_for_task(1, "design", "python-fastapi") is None


def test_invite_url_uses_portal_base(monkeypatch):
    monkeypatch.setattr(
        sim_service.settings, "CANDIDATE_PORTAL_BASE_URL", "https://portal.test"
    )
    assert sim_service.invite_url("abc") == "https://portal.test/candidate/session/abc"


@pytest.mark.asyncio
async def test_create_invite_handles_token_collisions(monkeypatch):
    class StubSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.added: CandidateSession | None = None

        def add(self, obj):
            self.added = obj

        async def commit(self):
            self.commits += 1
            raise IntegrityError("", {}, None)

        async def rollback(self):
            self.rollbacks += 1

    with pytest.raises(Exception) as excinfo:
        await sim_service.create_invite(
            StubSession(),
            simulation_id=1,
            payload=type("P", (), {"candidateName": "x", "inviteEmail": "y"}),
        )
    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_create_simulation_with_tasks_flow(async_session, monkeypatch):
    payload = type(
        "P",
        (),
        {
            "title": "Title",
            "role": "Role",
            "techStack": "Python",
            "seniority": "Mid",
            "focus": "Build",
            "templateKey": "python-fastapi",
        },
    )()
    user = type("U", (), {"company_id": 1, "id": 2})
    sim, tasks = await sim_service.create_simulation_with_tasks(
        async_session, payload, user
    )
    assert sim.id is not None
    assert len(tasks) == len(sim_service.DEFAULT_5_DAY_BLUEPRINT)
    # ensure tasks are sorted and refreshed
    assert tasks[0].day_index == 1


@pytest.mark.asyncio
async def test_create_invite_success(async_session):
    payload = type(
        "P", (), {"candidateName": "Jane", "inviteEmail": "jane@example.com"}
    )
    cs = await sim_service.create_invite(
        async_session, simulation_id=1, payload=payload, now=datetime.now(UTC)
    )
    assert cs.token
    assert cs.status == "not_started"


@pytest.mark.asyncio
async def test_require_owned_simulation_success(async_session):
    recruiter = await create_recruiter(async_session, email="owned@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    owned = await sim_service.require_owned_simulation(
        async_session, sim.id, recruiter.id
    )
    assert owned.id == sim.id


@pytest.mark.asyncio
async def test_list_with_candidate_counts(async_session):
    recruiter = await create_recruiter(async_session, email="counts@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    rows = await sim_service.list_simulations(async_session, recruiter.id)
    assert rows[0][0].id == sim.id


@pytest.mark.asyncio
async def test_list_candidates_with_profile(async_session):
    recruiter = await create_recruiter(async_session, email="list@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await sim_service.create_invite(
        async_session,
        simulation_id=sim.id,
        payload=type("P", (), {"candidateName": "a", "inviteEmail": "b@example.com"}),
    )
    rows = await sim_service.list_candidates_with_profile(async_session, sim.id)
    assert rows and rows[0][0].id == cs.id
