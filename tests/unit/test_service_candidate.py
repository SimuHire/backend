from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domains.submissions import service_candidate as svc
from app.integrations.github.actions_runner import ActionsRunResult
from app.integrations.github.client import GithubError
from app.integrations.github.workspaces import repository as workspace_repo
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


@pytest.mark.asyncio
async def test_record_run_result_persists_fields(async_session):
    recruiter = await create_recruiter(async_session, email="record@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)
    workspace = await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=tasks[1].template_repo or "",
        repo_full_name="org/record-repo",
        repo_id=999,
        default_branch="main",
        base_template_sha="base",
        created_at=now,
    )

    result = ActionsRunResult(
        status="failed",
        run_id=777,
        conclusion="failure",
        passed=0,
        failed=1,
        total=1,
        stdout="boom",
        stderr=None,
        head_sha="newsha",
        html_url="https://example.com/run/777",
        raw={"summary": {"status": "failed"}},
    )

    saved = await svc.record_run_result(async_session, workspace, result)
    assert saved.last_workflow_run_id == "777"
    assert saved.last_workflow_conclusion == "failure"
    assert saved.latest_commit_sha == "newsha"
    assert saved.last_test_summary_json


@pytest.mark.asyncio
async def test_ensure_workspace_creates_repo(async_session):
    recruiter = await create_recruiter(async_session, email="ws@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    class StubGithubClient:
        async def generate_repo_from_template(self, **_kw):
            return {"full_name": "org/new-repo", "id": 5, "default_branch": "main"}

        async def add_collaborator(
            self, repo_full_name, username, *, permission="push"
        ):
            return {"invited": username}

        async def get_branch(self, repo_full_name, branch):
            return {"commit": {"sha": "base-sha"}}

    ws = await svc.ensure_workspace(
        async_session,
        candidate_session=cs,
        task=tasks[1],
        github_client=StubGithubClient(),
        github_username="octocat",
        repo_prefix="prefix-",
        template_default_owner="org",
        now=datetime.now(UTC),
    )
    assert ws.repo_full_name == "org/new-repo"
    assert ws.base_template_sha == "base-sha"


@pytest.mark.asyncio
async def test_create_submission_conflict_raises(async_session):
    recruiter = await create_recruiter(async_session, email="dup@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    payload = SimpleNamespace(contentText="text")
    # seed one submission
    await svc.create_submission(
        async_session,
        cs,
        tasks[0],
        payload,
        now=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as excinfo:
        await svc.create_submission(
            async_session,
            cs,
            tasks[0],
            payload,
            now=datetime.now(UTC),
        )
    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_progress_after_submission_marks_complete(async_session):
    recruiter = await create_recruiter(async_session, email="done@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    now = datetime.now(UTC)
    for task in tasks:
        await svc.create_submission(
            async_session, cs, task, SimpleNamespace(contentText="x"), now=now
        )

    completed, total, is_complete = await svc.progress_after_submission(
        async_session, cs, now=now
    )
    assert is_complete is True
    assert completed == total == 5
    await async_session.refresh(cs)
    assert cs.status == "completed"


def test_validate_helpers_raise():
    cs = SimpleNamespace(simulation_id=1)
    task = SimpleNamespace(id=2, simulation_id=2)
    with pytest.raises(HTTPException):
        svc.ensure_task_belongs(task, cs)

    with pytest.raises(HTTPException):
        svc.ensure_in_order(SimpleNamespace(id=999), target_task_id=1)

    design_task = SimpleNamespace(type="design")
    with pytest.raises(HTTPException):
        svc.validate_submission_payload(design_task, SimpleNamespace(contentText=""))

    unknown_task = SimpleNamespace(type="mystery")
    with pytest.raises(HTTPException):
        svc.validate_submission_payload(unknown_task, SimpleNamespace(contentText="x"))

    with pytest.raises(HTTPException):
        svc.validate_github_username("bad user")

    with pytest.raises(HTTPException):
        svc.validate_repo_full_name("invalid")

    with pytest.raises(HTTPException):
        svc.validate_branch({"branch": "dict"})

    with pytest.raises(HTTPException):
        svc.validate_branch("../etc")


def test_is_code_task_and_branch_validation():
    assert svc.is_code_task(SimpleNamespace(type="code")) is True
    assert svc.is_code_task(SimpleNamespace(type="design")) is False
    with pytest.raises(HTTPException):
        svc.validate_branch("~weird")
    assert svc.validate_branch(None) is None


@pytest.mark.asyncio
async def test_ensure_workspace_existing_and_missing_template(
    monkeypatch, async_session
):
    recruiter = await create_recruiter(async_session, email="exist@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)
    existing = await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=tasks[0].id,
        template_repo_full_name=tasks[0].template_repo or "",
        repo_full_name="org/existing",
        repo_id=1,
        default_branch="main",
        base_template_sha=None,
        created_at=now,
    )

    class StubGithub:
        def __init__(self):
            self.invites: list[tuple[str, str]] = []

        async def add_collaborator(
            self, repo_full_name, username, *, permission="push"
        ):
            self.invites.append((repo_full_name, username))
            return {"invited": username}

    stub = StubGithub()
    ws = await svc.ensure_workspace(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        github_client=stub,
        github_username="octocat",
        repo_prefix="pref-",
        template_default_owner="org",
        now=now,
    )
    assert ws.id == existing.id
    assert stub.invites == [("org/existing", "octocat")]

    bad_task = SimpleNamespace(
        id=99, template_repo=" ", simulation_id=sim.id, type="code"
    )
    with pytest.raises(HTTPException):
        await svc.ensure_workspace(
            async_session,
            candidate_session=cs,
            task=bad_task,
            github_client=object(),
            github_username="octocat",
            repo_prefix="pref-",
            template_default_owner="org",
            now=now,
        )


@pytest.mark.asyncio
async def test_ensure_workspace_handles_branch_fetch_error(async_session):
    recruiter = await create_recruiter(async_session, email="branch@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    class StubGithub:
        async def generate_repo_from_template(self, **_kw):
            return {"full_name": "org/repo", "default_branch": "main", "id": 1}

        async def get_branch(self, *_a, **_k):
            raise GithubError("no branch")

        async def add_collaborator(self, *_a, **_k):
            return None

    ws = await svc.ensure_workspace(
        async_session,
        candidate_session=cs,
        task=tasks[1],
        github_client=StubGithub(),
        github_username="",
        repo_prefix="pref-",
        template_default_owner="org",
        now=datetime.now(UTC),
    )
    assert ws.base_template_sha is None


@pytest.mark.asyncio
async def test_load_task_or_404_branches(monkeypatch, async_session):
    class DummyTask:
        id = 1

    async def _return_task(db, task_id):
        return DummyTask()

    async def _return_none(db, task_id):
        return None

    monkeypatch.setattr(svc.tasks_repo, "get_by_id", _return_task)
    assert await svc.load_task_or_404(async_session, 1) is not None

    monkeypatch.setattr(svc.tasks_repo, "get_by_id", _return_none)
    with pytest.raises(HTTPException):
        await svc.load_task_or_404(async_session, 99)


@pytest.mark.asyncio
async def test_ensure_not_duplicate_and_in_order(monkeypatch):
    async def _dup_true(db, cs_id, task_id):
        return True

    async def _dup_false(db, cs_id, task_id):
        return False

    monkeypatch.setattr(svc.submissions_repo, "find_duplicate", _dup_false)
    # Should not raise
    svc.ensure_in_order(SimpleNamespace(id=1), target_task_id=1)

    monkeypatch.setattr(svc.submissions_repo, "find_duplicate", _dup_true)
    with pytest.raises(HTTPException):
        await svc.ensure_not_duplicate(None, 1, 1)

    with pytest.raises(HTTPException):
        svc.ensure_in_order(None, target_task_id=1)

    with pytest.raises(HTTPException):
        svc.ensure_in_order(SimpleNamespace(id=2), target_task_id=1)


@pytest.mark.asyncio
async def test_ensure_workspace_reuses_existing(async_session):
    recruiter = await create_recruiter(async_session, email="reuse@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    task = tasks[1]

    existing = await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=task.id,
        template_repo_full_name=task.template_repo,
        repo_full_name="owner/repo",
        repo_id=123,
        default_branch="main",
        base_template_sha="abc",
        created_at=datetime.now(UTC),
    )

    calls = []

    class DummyGithub:
        async def add_collaborator(self, repo_full_name, username):
            calls.append((repo_full_name, username))

        async def generate_repo_from_template(self, *a, **k):
            raise AssertionError("should not generate new repo")

    ws = await svc.ensure_workspace(
        async_session,
        candidate_session=cs,
        task=task,
        github_client=DummyGithub(),
        github_username="octocat",
        repo_prefix="pref-",
        template_default_owner="owner",
        now=datetime.now(UTC),
    )

    assert ws.id == existing.id
    assert calls == [("owner/repo", "octocat")]
