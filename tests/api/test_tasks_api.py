import json

import pytest
from sqlalchemy import delete, select

from app.domain import Submission, Task
from app.services.github.actions import ActionsRunResult
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_submit_rejects_expired_session(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="expired@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
        expires_in_days=-1,
    )

    task_id = tasks[0].id
    res = await async_client.post(
        f"/api/tasks/{task_id}/submit",
        headers={
            "x-candidate-token": cs.token,
            "x-candidate-session-id": str(cs.id),
        },
        json={"contentText": "should fail"},
    )
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_submit_after_completion_returns_409(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="done@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )

    # Seed submissions for all tasks to mark sim complete
    for task in tasks:
        await create_submission(
            async_session,
            candidate_session=cs,
            task=task,
            content_text="done",
        )
    await async_session.refresh(cs)

    task_id = tasks[-1].id
    res = await async_client.post(
        f"/api/tasks/{task_id}/submit",
        headers={
            "x-candidate-token": cs.token,
            "x-candidate-session-id": str(cs.id),
        },
        json={"contentText": "too late"},
    )
    assert res.status_code == 409
    assert res.json()["detail"] in {
        "Simulation already completed",
        "Task already submitted",
    }


@pytest.mark.asyncio
async def test_submit_returns_500_when_simulation_missing_tasks(
    async_client, async_session
):
    recruiter = await create_recruiter(async_session, email="notasks@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # Remove tasks to exercise guard
    await async_session.execute(delete(Task).where(Task.simulation_id == sim.id))
    await async_session.commit()

    res = await async_client.post(
        f"/api/tasks/{tasks[0].id}/submit",
        headers={
            "x-candidate-token": cs.token,
            "x-candidate-session-id": str(cs.id),
        },
        json={"contentText": "should error"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_submit_task_not_found(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="missingtask@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    res = await async_client.post(
        "/api/tasks/999999/submit",
        headers={
            "x-candidate-token": cs.token,
            "x-candidate-session-id": str(cs.id),
        },
        json={"contentText": "no task"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_submit_task_from_other_simulation(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="cross@sim.com")
    sim_a, tasks_a = await create_simulation(async_session, created_by=recruiter)
    sim_b, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim_b, status="in_progress"
    )

    # Use task from sim_a with session from sim_b -> 404
    res = await async_client.post(
        f"/api/tasks/{tasks_a[0].id}/submit",
        headers={
            "x-candidate-token": cs.token,
            "x-candidate-session-id": str(cs.id),
        },
        json={"contentText": "wrong sim"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_submit_unknown_task_type_errors(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="unk@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # Manually insert a task with unsupported type
    res_tasks = await async_session.execute(
        select(Task).where(Task.simulation_id == sim.id).order_by(Task.day_index)
    )
    for t in res_tasks.scalars():
        await async_session.delete(t)
    await async_session.commit()

    bad_task = Task(
        simulation_id=sim.id,
        day_index=1,
        type="behavioral",
        title="Unknown type",
        description="N/A",
    )
    async_session.add(bad_task)
    await async_session.commit()
    await async_session.refresh(bad_task)

    res = await async_client.post(
        f"/api/tasks/{bad_task.id}/submit",
        headers={
            "x-candidate-token": cs.token,
            "x-candidate-session-id": str(cs.id),
        },
        json={"contentText": "unknown"},
    )
    assert res.status_code == 500


@pytest.mark.asyncio
async def test_submit_code_task_persists_actions_results(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="code-submit@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    # Seed day 1 submission to unlock day 2 code task
    await create_submission(
        async_session, candidate_session=cs, task=tasks[0], content_text="day1"
    )
    await async_session.commit()

    actions_stubber(
        result=ActionsRunResult(
            status="failed",
            run_id=555,
            conclusion="failure",
            passed=1,
            failed=2,
            total=3,
            stdout="prints",
            stderr="boom",
            head_sha="abc123",
            html_url="https://example.com/run/555",
            raw=None,
        )
    )

    headers = candidate_header_factory(cs.id, cs.token)
    await async_client.post(
        f"/api/tasks/{tasks[1].id}/codespace/init",
        headers=headers,
        json={"githubUsername": "octocat"},
    )
    resp = await async_client.post(
        f"/api/tasks/{tasks[1].id}/submit",
        headers=headers,
        json={},
    )

    assert resp.status_code == 201, resp.text
    sub = await async_session.get(Submission, resp.json()["submissionId"])
    assert sub.tests_passed == 1
    assert sub.tests_failed == 2
    assert sub.last_run_at is not None
    assert sub.test_output
    payload = json.loads(sub.test_output)
    assert payload["status"] == "failed"
    assert payload["passed"] == 1
    assert payload["failed"] == 2
    assert payload["total"] == 3
    assert payload["stdout"] == "prints"
    assert payload["stderr"] == "boom"
    assert sub.commit_sha == "abc123"
    assert sub.workflow_run_id == "555"
    diff_summary = json.loads(sub.diff_summary_json or "{}")
    assert diff_summary["base"] == "base-sha-123"
    assert diff_summary["head"] == "abc123"
    assert "files" in diff_summary

    detail = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["diffSummary"] == diff_summary
    assert detail_body["diffUrl"].endswith("base-sha-123...abc123")


@pytest.mark.asyncio
async def test_submit_text_task_leaves_test_fields_null(
    async_client, async_session, candidate_header_factory
):
    recruiter = await create_recruiter(async_session, email="text-submit@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    headers = candidate_header_factory(cs.id, cs.token)
    resp = await async_client.post(
        f"/api/tasks/{tasks[0].id}/submit",
        headers=headers,
        json={"contentText": "design answer"},
    )

    assert resp.status_code == 201, resp.text
    sub = await async_session.get(Submission, resp.json()["submissionId"])
    assert sub.tests_passed is None
    assert sub.tests_failed is None
    assert sub.test_output is None
    assert sub.last_run_at is None


@pytest.mark.asyncio
async def test_submit_code_task_actions_error_returns_502_no_submission(
    async_client, async_session, candidate_header_factory, actions_stubber
):
    recruiter = await create_recruiter(async_session, email="actions-err@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    # seed day 1 to reach day 2 code task
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
        f"/api/tasks/{tasks[1].id}/submit",
        headers=headers,
        json={},
    )

    assert resp.status_code == 502
    result = await async_session.execute(
        select(Submission).where(
            Submission.candidate_session_id == cs.id, Submission.task_id == tasks[1].id
        )
    )
    assert result.scalar_one_or_none() is None
