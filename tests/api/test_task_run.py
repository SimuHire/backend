import pytest

from app.api.routes.candidate import submissions as candidate_submissions
from app.main import app
from app.services.github.actions import ActionsRunResult
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
        async_session, simulation=sim, status="in_progress"
    )
    # Complete earlier tasks to allow day 3 debug
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[1], content_text="day2"
    )
    await async_session.commit()

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        f"/api/tasks/{tasks[2].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)

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
        async_session, simulation=sim, status="in_progress"
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

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        f"/api/tasks/{tasks[2].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)

    assert resp.status_code == 500
    assert "template repository is not configured" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_run_tests_returns_actions_result(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="run-tests@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
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

    headers = candidate_header_factory(cs.id, cs.token)
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

    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["passed"] == 2
    assert body["failed"] == 1
    assert body["total"] == 3
    assert body["status"] == "failed"
    assert body["runId"] == 111
    assert body["commitSha"] == "abc123"


@pytest.mark.asyncio
async def test_run_tests_invalid_task_404(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="run-404@sim.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await async_session.commit()

    actions_stubber()

    headers = candidate_header_factory(cs.id, cs.token)
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
    assert resp.json()["detail"] == "Missing candidate session headers"


@pytest.mark.asyncio
async def test_run_tests_handles_actions_error(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="actions-error@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    class Boom(Exception):
        pass

    actions_stubber(error=Boom("boom"))

    headers = candidate_header_factory(cs.id, cs.token)
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

    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)

    assert resp.status_code == 502
    assert "GitHub unavailable" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_run_result_returns_parsed_counts(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    actions_stubber()
    recruiter = await create_recruiter(async_session, email="run-get@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    headers = candidate_header_factory(cs.id, cs.token)
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

    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)

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
        async_session, simulation=sim, status="in_progress"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    headers = candidate_header_factory(cs.id, cs.token)
    await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )

    resp = await async_client.get(
        f"/api/tasks/{tasks[1].id}/run/{timed_out.run_id}",
        headers=headers,
    )

    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["timeout"] is True
    assert data["runId"] == timed_out.run_id
