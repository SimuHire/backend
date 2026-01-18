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
        submitted_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter1.email},
    )
    # prefer 404 to avoid leaking existence
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Submission not found"
    combined = json.dumps(body)
    assert "Other Candidate" not in combined


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
    assert data["output"].get("summary") is None
    assert data["artifactName"] == "tenon-test-results"
    assert data["artifactPresent"] is True


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
    assert "output" not in (found.get("testResults") or {})
    tr = found.get("testResults") or {}
    assert tr.get("artifactName") in (None, "tenon-test-results")
    assert tr.get("artifactPresent") in (None, True)


@pytest.mark.asyncio
async def test_recruiter_list_scoped_to_owner(
    async_client, async_session: AsyncSession
):
    recruiter1 = await create_recruiter(async_session, email="owner1@test.com")
    recruiter2 = await create_recruiter(async_session, email="owner2@test.com")
    sim1, tasks1 = await create_simulation(async_session, created_by=recruiter1)
    sim2, tasks2 = await create_simulation(async_session, created_by=recruiter2)

    cs1 = await create_candidate_session(async_session, simulation=sim1)
    cs2 = await create_candidate_session(async_session, simulation=sim2)

    sub1 = await create_submission(
        async_session,
        candidate_session=cs1,
        task=tasks1[0],
        submitted_at=datetime.now(UTC),
    )
    await create_submission(
        async_session,
        candidate_session=cs2,
        task=tasks2[0],
        submitted_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        "/api/submissions",
        headers={"x-dev-user-email": recruiter1.email},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert {item["submissionId"] for item in items} == {sub1.id}


@pytest.mark.asyncio
async def test_recruiter_submission_detail_includes_artifact_metadata(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(async_session, email="detail@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim, status="started")

    long_stdout = "x" * 21000
    output = {
        "status": "failed",
        "passed": 2,
        "failed": 1,
        "total": 3,
        "stdout": long_stdout,
        "stderr": "short error",
        "runId": 777,
        "conclusion": "failure",
        "summary": {"note": "check"},
    }
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        code_repo_path="acme/repo1",
        commit_sha="deadbeef",
        workflow_run_id="42",
        diff_summary_json=json.dumps({"base": "base-branch", "head": "feature"}),
        test_output=json.dumps(output),
        last_run_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["workflowUrl"].endswith("/actions/runs/42")
    assert body["commitUrl"].endswith("/commit/deadbeef")
    assert body["diffUrl"].endswith("/compare/base-branch...feature")
    assert body["code"]["repoFullName"] == "acme/repo1"

    test_results = body["testResults"]
    assert test_results["status"] == "failed"
    assert test_results["total"] == 3
    assert test_results["runId"] == 777
    assert test_results["workflowRunId"] == "42"
    assert test_results["conclusion"] == "failure"
    assert test_results["summary"] == {"note": "check"}
    assert test_results["runStatus"] is None
    assert test_results["artifactName"] == "tenon-test-results"
    assert test_results["artifactPresent"] is True
    assert test_results["stdout"].endswith("(truncated)")
    assert test_results["stdoutTruncated"] is True
    assert len(test_results["stdout"]) < len(long_stdout)
    assert test_results["output"]["stdout"].endswith("(truncated)")
    assert test_results["stderr"] == "short error"
    assert test_results["stderrTruncated"] is False


@pytest.mark.asyncio
async def test_recruiter_submission_list_includes_test_results(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(async_session, email="listmeta@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim, status="started")

    output = {
        "status": "passed",
        "passed": 4,
        "failed": 0,
        "total": 4,
        "stdout": "great",
        "stderr": "",
        "runId": 991,
        "conclusion": "success",
    }
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        code_repo_path="acme/repo2",
        commit_sha="cafebabe",
        workflow_run_id="321",
        diff_summary_json=json.dumps({"base": "main", "head": "feature2"}),
        test_output=json.dumps(output),
        last_run_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        "/api/submissions",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["submissionId"] == sub.id)
    test_results = item["testResults"]
    assert test_results["status"] == "passed"
    assert test_results["passed"] == 4
    assert test_results["failed"] == 0
    assert test_results["total"] == 4
    assert test_results["runStatus"] is None
    assert test_results["workflowUrl"].endswith("/actions/runs/321")
    assert test_results["commitUrl"].endswith("/commit/cafebabe")
    assert item["diffUrl"].endswith("/compare/main...feature2")
    assert "output" not in test_results or test_results["output"] is None
    assert test_results["stdoutTruncated"] is False
    assert test_results["stderrTruncated"] is False
    assert test_results["artifactName"] == "tenon-test-results"
    assert test_results["artifactPresent"] is True


@pytest.mark.asyncio
async def test_recruiter_submission_handles_missing_artifacts(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(async_session, email="nulls@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim, status="started")
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        submitted_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["workflowUrl"] is None
    assert payload["commitUrl"] is None
    assert payload["diffUrl"] is None
    assert payload["testResults"] is None


@pytest.mark.asyncio
async def test_recruiter_submission_redacts_tokens(
    async_client, async_session: AsyncSession
):
    recruiter = await create_recruiter(async_session, email="redact@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim, status="started")
    output = {
        "status": "failed",
        "passed": 0,
        "failed": 1,
        "total": 1,
        "stdout": "fail ghp_1234567890abcdef",
        "stderr": "Authorization: Bearer SECRET",
    }
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        code_repo_path="acme/repo3",
        workflow_run_id="789",
        diff_summary_json=json.dumps({"base": "a", "head": "b"}),
        test_output=json.dumps(output),
        last_run_at=datetime.now(UTC),
    )

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["testResults"]
    combined = json.dumps(body)
    assert "ghp_1234567890abcdef" not in combined
    assert "Authorization: Bearer SECRET" not in combined
    assert "[redacted]" in combined
