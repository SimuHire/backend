import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies.github_native import get_github_client
from app.api.dependencies.notifications import get_email_service
from app.domains import CandidateSession
from app.domains.github_native.client import GithubError
from app.domains.github_native.workspaces.workspace import Workspace
from app.infra.notifications.email_provider import MemoryEmailProvider
from app.services.email import EmailService
from tests.factories import create_recruiter, create_simulation


@pytest.mark.asyncio
async def test_create_simulation_seeds_default_tasks(
    async_client, async_session, auth_header_factory
):
    recruiter = await create_recruiter(
        async_session, email="owner1@example.com", name="Owner One"
    )

    payload = {
        "title": "Backend Node Simulation",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Build a new API and iterate over 5 days",
    }

    res = await async_client.post(
        "/api/simulations", json=payload, headers=auth_header_factory(recruiter)
    )
    assert res.status_code == 201, res.text

    body = res.json()
    assert body["title"] == payload["title"]
    assert len(body["tasks"]) == 5
    assert [t["day_index"] for t in body["tasks"]] == [1, 2, 3, 4, 5]
    assert body["tasks"][0]["type"] == "design"


@pytest.mark.asyncio
async def test_list_simulations_scoped_to_owner(
    async_client, async_session, auth_header_factory
):
    owner = await create_recruiter(
        async_session, email="owner@example.com", name="Owner Recruiter"
    )
    other = await create_recruiter(
        async_session, email="other@example.com", name="Other Recruiter"
    )

    owned_sim, _ = await create_simulation(
        async_session, created_by=owner, title="Owner Sim"
    )
    await create_simulation(async_session, created_by=other, title="Other Sim")

    res = await async_client.get("/api/simulations", headers=auth_header_factory(owner))
    assert res.status_code == 200, res.text

    ids = {item["id"] for item in res.json()}
    assert owned_sim.id in ids
    # cross-company sim must be hidden
    assert all(item["title"] != "Other Sim" for item in res.json())


@pytest.mark.asyncio
async def test_invite_sends_email_and_tracks_status(
    async_client, async_session, auth_header_factory, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="notify@app.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")

    with override_dependencies({get_email_service: lambda: email_service}):
        res = await async_client.post(
            f"/api/simulations/{sim.id}/invite",
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
            headers=auth_header_factory(recruiter),
        )

    assert res.status_code == 201, res.text

    cs = (await async_session.execute(select(CandidateSession))).scalar_one()
    assert cs.invite_email_status == "sent"
    assert cs.invite_email_sent_at is not None
    assert len(provider.sent) == 1
    assert provider.sent[0].to == cs.invite_email

    list_res = await async_client.get(
        f"/api/simulations/{sim.id}/candidates",
        headers=auth_header_factory(recruiter),
    )
    assert list_res.status_code == 200
    body = list_res.json()[0]
    assert body["inviteEmailStatus"] == "sent"
    assert body["inviteEmailSentAt"] is not None


@pytest.mark.asyncio
async def test_invite_preprovisions_day2_day3_workspaces(
    async_client, async_session, auth_header_factory, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="preprov@app.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)

    day2_tasks = [t for t in tasks if t.day_index == 2]
    day3_tasks = [t for t in tasks if t.day_index == 3]
    assert day2_tasks and day3_tasks
    day2_tasks[0].type = "code"
    day3_tasks[0].type = "debug"
    await async_session.commit()

    class StubGithubClient:
        def __init__(self):
            self.generated: list[tuple[str, str, str | None]] = []

        async def generate_repo_from_template(
            self, *, template_full_name, new_repo_name, owner=None, private=True
        ):
            self.generated.append((template_full_name, new_repo_name, owner))
            return {
                "full_name": f"{owner}/{new_repo_name}",
                "id": 100 + len(self.generated),
                "default_branch": "main",
            }

        async def get_branch(self, repo_full_name, branch):
            return {"commit": {"sha": "base-sha"}}

        async def add_collaborator(
            self, repo_full_name, username, *, permission="push"
        ):
            return {"ok": True}

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")
    stub_client = StubGithubClient()

    with override_dependencies(
        {
            get_email_service: lambda: email_service,
            get_github_client: lambda: stub_client,
        }
    ):
        res = await async_client.post(
            f"/api/simulations/{sim.id}/invite",
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
            headers=auth_header_factory(recruiter),
        )

    assert res.status_code == 201, res.text

    cs = (await async_session.execute(select(CandidateSession))).scalar_one()
    workspaces = (
        (
            await async_session.execute(
                select(Workspace).where(Workspace.candidate_session_id == cs.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(stub_client.generated) == 2
    expected_ids = {day2_tasks[0].id, day3_tasks[0].id}
    assert {ws.task_id for ws in workspaces} == expected_ids
    assert all(ws.base_template_sha == "base-sha" for ws in workspaces)


@pytest.mark.asyncio
async def test_invite_github_failure_reuses_candidate_session(
    async_client, async_session, auth_header_factory, override_dependencies, monkeypatch
):
    recruiter = await create_recruiter(async_session, email="fail@app.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    day2_task = next(t for t in tasks if t.day_index == 2)
    day3_task = next(t for t in tasks if t.day_index == 3)
    day2_task.type = "code"
    day3_task.type = "debug"
    day2_task_id = day2_task.id
    day3_task_id = day3_task.id
    await async_session.commit()

    class FailingGithubClient:
        async def generate_repo_from_template(self, **_kw):
            raise GithubError("boom")

        async def get_branch(self, *_a, **_k):
            return {"commit": {"sha": "base-sha"}}

        async def add_collaborator(self, *_a, **_k):
            return {"ok": True}

    class SuccessGithubClient:
        async def generate_repo_from_template(
            self, *, template_full_name, new_repo_name, owner=None, private=True
        ):
            return {
                "full_name": f"{owner}/{new_repo_name}",
                "id": 200,
                "default_branch": "main",
            }

        async def get_branch(self, repo_full_name, branch):
            return {"commit": {"sha": "base-sha"}}

        async def add_collaborator(self, *_a, **_k):
            return {"ok": True}

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")

    with override_dependencies(
        {
            get_email_service: lambda: email_service,
            get_github_client: lambda: FailingGithubClient(),
        }
    ):
        res = await async_client.post(
            f"/api/simulations/{sim.id}/invite",
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
            headers=auth_header_factory(recruiter),
        )
    assert res.status_code == 502, res.text

    existing = (
        (
            await async_session.execute(
                select(CandidateSession).where(
                    CandidateSession.invite_email == "jane@example.com"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(existing) == 1

    fail_once = True
    original_commit = async_session.commit

    async def _commit_with_integrity_error():
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise IntegrityError("", {}, None)
        return await original_commit()

    monkeypatch.setattr(async_session, "commit", _commit_with_integrity_error)

    with override_dependencies(
        {
            get_email_service: lambda: email_service,
            get_github_client: lambda: SuccessGithubClient(),
        }
    ):
        res = await async_client.post(
            f"/api/simulations/{sim.id}/invite",
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
            headers=auth_header_factory(recruiter),
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["candidateSessionId"] == existing[0].id

    workspaces = (
        (
            await async_session.execute(
                select(Workspace).where(
                    Workspace.candidate_session_id == existing[0].id
                )
            )
        )
        .scalars()
        .all()
    )
    assert {ws.task_id for ws in workspaces} == {day2_task_id, day3_task_id}


@pytest.mark.asyncio
async def test_invite_candidate_rejects_unowned_simulation(
    async_client, async_session, auth_header_factory
):
    owner = await create_recruiter(async_session, email="owner@example.com")
    outsider = await create_recruiter(async_session, email="outsider@example.com")
    sim, _ = await create_simulation(async_session, created_by=owner)

    res = await async_client.post(
        f"/api/simulations/{sim.id}/invite",
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
        headers=auth_header_factory(outsider),
    )
    assert res.status_code == 404
