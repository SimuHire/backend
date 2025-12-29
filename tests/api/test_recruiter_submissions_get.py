import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_recruiter_can_fetch_known_submission(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(
        async_session, email="recruiter1@test.com", name="Recruiter One"
    )
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    task = tasks[0]

    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        candidate_name="Jane Candidate",
        invite_email="a@b.com",
        status="in_progress",
    )

    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=task,
        content_text="my design answer",
        code_blob=None,
        submitted_at=datetime.now(UTC),
        tests_passed=3,
        tests_failed=0,
        test_output="ok",
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["submissionId"] == sub.id
    assert data["candidateSessionId"] == cs.id
    assert data["task"]["taskId"] == task.id
    assert data["contentText"] == "my design answer"
    assert data["testResults"]["status"] == "passed"
    assert data["testResults"]["passed"] == 3
    assert data["testResults"]["failed"] == 0


@pytest.mark.asyncio
async def test_recruiter_cannot_access_other_recruiters_submission(
    async_client, async_session: AsyncSession
):
    recruiter1 = await create_recruiter(
        async_session, email="recruiter1@test.com", name="Recruiter One"
    )
    recruiter2 = await create_recruiter(
        async_session, email="recruiter2@test.com", name="Recruiter Two"
    )

    sim, tasks = await create_simulation(async_session, created_by=recruiter2)
    task = tasks[0]

    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        candidate_name="Other Candidate",
        invite_email="x@y.com",
        status="in_progress",
    )

    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=task,
        code_blob="console.log('secret')",
        submitted_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter1.email},
    )
    # prefer 404 to avoid leaking existence
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_recruiter_parses_structured_test_output(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(
        async_session, email="struct@test.com", name="Struct Recruiter"
    )
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    task = tasks[1]
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    output = {
        "status": "failed",
        "passed": 1,
        "failed": 2,
        "total": 3,
        "stdout": "prints",
        "stderr": "boom",
        "timeout": False,
    }
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=task,
        content_text=None,
        code_blob="code",
        tests_passed=None,
        tests_failed=None,
        test_output=json.dumps(output),
        last_run_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["testResults"]
    assert data["status"] == "failed"
    assert data["passed"] == 1
    assert data["failed"] == 2
    assert data["total"] == 3
    assert data["output"]["stdout"] == "prints"
    assert data["output"]["stderr"] == "boom"


@pytest.mark.asyncio
async def test_missing_submission_returns_404(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(
        async_session, email="recruiter1@test.com", name="Recruiter One"
    )

    resp = await async_client.get(
        "/api/submissions/999999",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_recruiter_list_includes_links(async_client, async_session: AsyncSession):
    recruiter = await create_recruiter(
        async_session, email="links@test.com", name="Recruiter Links"
    )
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        code_blob=None,
        code_repo_path="org/repo",
        commit_sha="abc123",
        workflow_run_id="555",
        diff_summary_json=json.dumps({"base": "base1", "head": "head1"}),
        submitted_at=datetime.now(UTC),
    )
    resp = await async_client.get(
        "/api/submissions",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"items"}
    items = body["items"]
    found = next(i for i in items if i["submissionId"] == sub.id)
    assert found["repoFullName"] == "org/repo"
    assert found["workflowRunId"] == "555"
    assert found["commitSha"] == "abc123"
    assert found["workflowUrl"]
    assert found["commitUrl"]
    assert found["diffUrl"]
