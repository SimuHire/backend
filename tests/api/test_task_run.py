from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.api.routes import tasks_codespaces as candidate_submissions
from app.domains.github_native.actions_runner import ActionsRunResult
from app.domains.github_native.client import GithubError
from app.domains.github_native.workspaces import repository as workspace_repo
from app.domains.github_native.workspaces.workspace import Workspace
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_codespace_init_works_for_debug_task(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    actions_stubber()
    recruiter = await create_recruiter(async_session, email="debug-task@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    # Complete earlier tasks to allow day 3 debug
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[1], content_text="day2"
    )
    await async_session.commit()

    headers = candidate_header_factory(cs)
    resp = await async_client.post(
        f"/api/tasks/{tasks[2].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["repoFullName"]
    assert body["workspaceId"]


@pytest.mark.asyncio
async def test_codespace_init_missing_template_repo_returns_500(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    actions_stubber()
    recruiter = await create_recruiter(async_session, email="missing-template@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    # Complete earlier tasks to allow day 3 debug
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[1], content_text="day2"
    )
    # Remove template repo for debug task to trigger error
    tasks[2].template_repo = None
    await async_session.commit()

    headers = candidate_header_factory(cs)
    resp = await async_client.post(
        f"/api/tasks/{tasks[2].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    assert resp.status_code == 500
    assert "template repository is not configured" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_codespace_init_reuses_existing_workspace_and_skips_github(
    async_client, async_session, candidate_header_factory, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="reuse@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    # Complete day 1 to unlock day 2 code task
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    existing = await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=tasks[1].template_repo or "",
        repo_full_name="org/precreated-repo",
        repo_id=321,
        default_branch="main",
        base_template_sha="base-precreated",
        created_at=datetime.now(UTC),
    )

    calls: dict[str, int] = {"generate": 0}

    class CountingGithubClient:
        async def generate_repo_from_template(
            self,
            *,
            template_full_name: str,
            new_repo_name: str,
            owner=None,
            private=True,
        ):
            calls["generate"] += 1
            raise AssertionError("generate_repo_from_template should not be called")

        async def add_collaborator(
            self, repo_full_name: str, username: str, *, permission: str = "push"
        ):
            calls.setdefault("collab", 0)
            calls["collab"] += 1

        async def get_branch(self, repo_full_name: str, branch: str):
            return {}

        async def get_compare(self, repo_full_name: str, base: str, head: str):
            return {}

    with override_dependencies(
        {candidate_submissions.get_github_client: lambda: CountingGithubClient()}
    ):
        headers = candidate_header_factory(cs)
        resp = await async_client.post(
            f"/api/tasks/{tasks[1].id}/codespace/init",
            headers=headers,
            json={"githubUsername": "octocat"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspaceId"] == existing.id
    assert body["repoFullName"] == existing.repo_full_name
    assert calls["generate"] == 0

    rows = await async_session.execute(
        select(Workspace).where(
            Workspace.candidate_session_id == cs.id, Workspace.task_id == tasks[1].id
        )
    )
    assert len(list(rows.scalars())) == 1


@pytest.mark.asyncio
async def test_codespace_init_maps_github_errors_to_502(
    async_client, async_session, candidate_header_factory, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="gh-error@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    class ErrorGithubClient:
        async def generate_repo_from_template(self, **_kwargs):
            raise GithubError("Bad credentials", status_code=403)

    with override_dependencies(
        {candidate_submissions.get_github_client: lambda: ErrorGithubClient()}
    ):
        headers = candidate_header_factory(cs)
        resp = await async_client.post(
            f"/api/tasks/{tasks[1].id}/codespace/init",
            headers=headers,
            json={"githubUsername": "octocat"},
        )

    assert resp.status_code == 502
    assert "GitHub unavailable" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_run_tests_returns_actions_result(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="run-tests@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    stub_result = ActionsRunResult(
        status="failed",
        run_id=111,
        conclusion="failure",
        passed=2,
        failed=1,
        total=3,
        stdout="out",
        stderr=None,
        head_sha="abc123",
        html_url="https://example.com/run/111",
        raw=None,
    )
    actions_stubber(result=stub_result)

    headers = candidate_header_factory(cs)
    # Init workspace first
    init_resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )
    assert init_resp.status_code == 200, init_resp.text

    resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["passed"] == 2
    assert body["failed"] == 1
    assert body["total"] == 3
    assert body["status"] == "failed"
    assert body["runId"] == 111
    assert body["commitSha"] == "abc123"
    assert body["timeout"] is False


@pytest.mark.asyncio
async def test_run_tests_rate_limited_when_prod_env(
    async_client, async_session, candidate_header_factory, actions_stubber, monkeypatch
):
    monkeypatch.setattr(candidate_submissions.settings, "ENV", "prod")
    candidate_submissions._RATE_LIMIT_STORE.clear()
    original_rule = dict(candidate_submissions._RATE_LIMIT_RULE)
    candidate_submissions._RATE_LIMIT_RULE["run"] = (1, 60.0)

    recruiter = await create_recruiter(async_session, email="rate@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    actions_stubber()
    headers = candidate_header_factory(cs)
    await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    first = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={},
    )
    assert first.status_code == 200, first.text

    second = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={},
    )
    assert second.status_code == 429

    # reset ENV/rules to avoid bleed
    monkeypatch.setattr(candidate_submissions.settings, "ENV", "local")
    candidate_submissions._RATE_LIMIT_RULE.update(original_rule)


@pytest.mark.asyncio
async def test_run_tests_invalid_task_404(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="run-404@sim.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await async_session.commit()

    actions_stubber()

    headers = candidate_header_factory(cs)
    resp = await async_client.post(
        "/api/tasks/99999/run",
        headers=headers,
        json={},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_tests_missing_headers_returns_401(async_client):
    resp = await async_client.post("/api/tasks/1/run", json={})
    assert resp.status_code == 401
    assert resp.json()["detail"] in {
        "Missing candidate session headers",
        "Not authenticated",
    }


@pytest.mark.asyncio
async def test_run_tests_handles_actions_error(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="actions-error@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    class Boom(Exception):
        pass

    actions_stubber(error=Boom("boom"))

    headers = candidate_header_factory(cs)
    await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )
    resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={},
    )

    assert resp.status_code == 502
    assert "GitHub unavailable" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_codespace_status_returns_summary(
    async_client, async_session, candidate_header_factory
):
    recruiter = await create_recruiter(async_session, email="status@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    workspace = await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=tasks[1].template_repo or "",
        repo_full_name="org/status-repo",
        repo_id=111,
        default_branch="main",
        base_template_sha="base",
        created_at=datetime.now(UTC),
    )
    workspace.last_test_summary_json = "{not-json"
    await async_session.commit()

    headers = candidate_header_factory(cs)
    resp = await async_client.get(
        f"/api/tasks/{tasks[1].id}/codespace/status",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["repoFullName"] == "org/status-repo"
    assert data["lastTestSummary"] is None
    assert data["codespaceUrl"] == "https://codespaces.new/org/status-repo?quickstart=1"


@pytest.mark.asyncio
async def test_get_run_result_returns_parsed_counts(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    actions_stubber()
    recruiter = await create_recruiter(async_session, email="run-get@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    headers = candidate_header_factory(cs)
    await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    # fetch_run_result uses the stubbed runner
    resp = await async_client.get(
        f"/api/tasks/{tasks[1].id}/run/123",
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["runId"] == 123
    assert body["passed"] == 1
    assert body["failed"] == 0
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_get_run_result_marks_timeout(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    timed_out = ActionsRunResult(
        status="running",
        run_id=777,
        conclusion="timed_out",
        passed=0,
        failed=0,
        total=0,
        stdout=None,
        stderr=None,
        head_sha="abc123",
        html_url="https://example.com/run/777",
        raw=None,
    )
    actions_stubber(result=timed_out)
    recruiter = await create_recruiter(async_session, email="run-timeout@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    headers = candidate_header_factory(cs)
    await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    resp = await async_client.get(
        f"/api/tasks/{tasks[1].id}/run/{timed_out.run_id}",
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["timeout"] is True
    assert data["runId"] == timed_out.run_id


@pytest.mark.asyncio
async def test_get_run_result_github_error_maps_to_502(
    async_client, async_session, candidate_header_factory, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="run-fetch-err@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    class ErrorRunner:
        async def fetch_run_result(self, **_kwargs):
            raise GithubError("nope")

    class StubGithubClient:
        async def generate_repo_from_template(
            self,
            *,
            template_full_name: str,
            new_repo_name: str,
            owner=None,
            private=True,
        ):
            return {
                "full_name": f"org/{new_repo_name}",
                "id": 1,
                "default_branch": "main",
            }

        async def add_collaborator(
            self, repo_full_name: str, username: str, *, permission: str = "push"
        ):
            return {"ok": True}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "base"}}

        async def get_compare(self, repo_full_name: str, base: str, head: str):
            return {}

    with override_dependencies(
        {
            candidate_submissions.get_actions_runner: lambda: ErrorRunner(),
            candidate_submissions.get_github_client: lambda: StubGithubClient(),
        }
    ):
        headers = candidate_header_factory(cs)
        await async_client.post(
            f"/api/tasks/{tasks[1].id}/codespace/init",
            headers=headers,
            json={"githubUsername": "octocat"},
        )
        resp = await async_client.get(
            f"/api/tasks/{tasks[1].id}/run/9999",
            headers=headers,
        )

    assert resp.status_code == 502
