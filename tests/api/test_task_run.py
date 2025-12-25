import pytest

from app.api.routes.candidate import submissions as candidate_submissions
from app.main import app
from app.services.sandbox_client import SandboxError, SandboxRunResult
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


class FakeSandboxClient:
    def __init__(
        self,
        *,
        result: SandboxRunResult | None = None,
        error: Exception | None = None,
    ):
        self._result = result
        self._error = error

    async def run_tests(self, **_kwargs):
        if self._error:
            raise self._error
        return self._result


@pytest.mark.asyncio
async def test_run_tests_returns_counts(
    async_client, async_session, candidate_header_factory
):
    recruiter = await create_recruiter(async_session, email="run-tests@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    # Seed day 1 submission so current task is day 2 (code)
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    captured = {"task_ref": None}

    class CapturingClient:
        def __init__(self, result):
            self._result = result

        async def run_tests(self, **kwargs):
            captured["task_ref"] = kwargs.get("task_ref")
            return self._result

    fake_result = SandboxRunResult(
        status="failed",
        passed=2,
        failed=1,
        total=3,
        stdout="out",
        stderr="",
        duration_ms=None,
        raw=None,
    )
    app.dependency_overrides[candidate_submissions.get_sandbox_client] = (
        lambda: CapturingClient(fake_result)
    )

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={"codeBlob": "console.log('hi')"},
    )

    app.dependency_overrides.pop(candidate_submissions.get_sandbox_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["passed"] == 2
    assert body["failed"] == 1
    assert body["total"] == 3
    assert body["status"] == "failed"
    scenario_prefix = (
        (sim.scenario_template or sim.focus or "default")
        .strip()
        .replace(" ", "-")
        .lower()
    )

    task = tasks[1]
    day_val = None
    for attr in ("day_index", "day", "day_number"):
        if hasattr(task, attr):
            val = getattr(task, attr, None)
            if val is not None:
                day_val = int(val)
                break
    if day_val is None:
        for attr in ("order", "position", "sequence"):
            if hasattr(task, attr):
                val = getattr(task, attr, None)
                if val is not None:
                    day_val = int(val)
                    break
    if day_val is None:
        day_val = 1
    if 0 <= day_val <= 4:
        day_val += 1
    if day_val <= 0:
        day_val = 1

    expected_ref = f"{scenario_prefix}-day{day_val}-code"
    assert captured["task_ref"] == expected_ref


@pytest.mark.asyncio
async def test_run_tests_invalid_task_404(
    async_client, async_session, candidate_header_factory
):
    recruiter = await create_recruiter(async_session, email="run-404@sim.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await async_session.commit()

    app.dependency_overrides[candidate_submissions.get_sandbox_client] = (
        lambda: FakeSandboxClient(
            result=SandboxRunResult(
                status="passed",
                passed=1,
                failed=0,
                total=1,
                stdout="",
                stderr="",
                duration_ms=None,
                raw=None,
            )
        )
    )

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        "/api/tasks/99999/run",
        headers=headers,
        json={"codeBlob": "print('hi')"},
    )

    app.dependency_overrides.pop(candidate_submissions.get_sandbox_client, None)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_tests_missing_headers_returns_401(async_client):
    resp = await async_client.post("/api/tasks/1/run", json={"codeBlob": "print('hi')"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing candidate session headers"


@pytest.mark.asyncio
async def test_run_tests_handles_sandbox_error(
    async_client, async_session, candidate_header_factory
):
    recruiter = await create_recruiter(async_session, email="sandbox-error@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    app.dependency_overrides[candidate_submissions.get_sandbox_client] = (
        lambda: FakeSandboxClient(error=SandboxError("boom"))
    )

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={"codeBlob": "console.log('hi')"},
    )

    app.dependency_overrides.pop(candidate_submissions.get_sandbox_client, None)

    assert resp.status_code == 502
    assert "Sandbox unavailable" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_run_tests_handles_unexpected_exception(
    async_client, async_session, candidate_header_factory
):
    recruiter = await create_recruiter(async_session, email="sandbox-unknown@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    class BoomClient:
        async def run_tests(self, **_kwargs):
            raise RuntimeError("boom")

    app.dependency_overrides[candidate_submissions.get_sandbox_client] = (
        lambda: BoomClient()
    )

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/run",
        headers=headers,
        json={"codeBlob": "console.log('hi')"},
    )

    app.dependency_overrides.pop(candidate_submissions.get_sandbox_client, None)

    assert resp.status_code == 502
    assert "Sandbox unavailable" in resp.json()["detail"]
