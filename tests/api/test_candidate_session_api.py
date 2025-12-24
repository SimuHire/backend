from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.task import Task
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_resolve_session_transitions_to_in_progress(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="resolve@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    assert cs.status == "not_started"
    assert cs.started_at is None

    res = await async_client.get(f"/api/candidate/session/{cs.token}")
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["status"] == "in_progress"
    assert body["candidateSessionId"] == cs.id

    await async_session.refresh(cs)
    assert cs.status == "in_progress"
    assert cs.started_at is not None


@pytest.mark.asyncio
async def test_current_task_marks_complete_when_all_tasks_done(
    async_client, async_session
):
    recruiter = await create_recruiter(async_session, email="progress@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
        started_at=datetime.now(UTC) - timedelta(hours=1),
    )

    # Seed submissions for all tasks to mimic completion.
    for task in tasks:
        await create_submission(
            async_session,
            candidate_session=cs,
            task=task,
            content_text=f"Answer for day {task.day_index}",
        )

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={"x-candidate-token": cs.token},
    )
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["isComplete"] is True
    assert body["currentDayIndex"] is None
    assert body["currentTask"] is None
    assert body["progress"]["completed"] == len(tasks)

    await async_session.refresh(cs)
    assert cs.status == "completed"
    assert cs.completed_at is not None


@pytest.mark.asyncio
async def test_get_current_task_respects_expiry(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="expired@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        expires_in_days=-1,
        status="in_progress",
        started_at=datetime.now(UTC) - timedelta(days=2),
    )

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={"x-candidate-token": cs.token},
    )
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_resolve_invalid_token(async_client):
    res = await async_client.get("/api/candidate/session/" + "x" * 24)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_resolve_expired_token_returns_410(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="expired-resolve@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        expires_in_days=-1,
        status="not_started",
    )

    res = await async_client.get(f"/api/candidate/session/{cs.token}")
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_current_task_token_mismatch(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="tm@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={"x-candidate-token": "wrong"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_current_task_no_tasks_returns_500(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="notasks@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # Remove all tasks to trigger guard
    await async_session.execute(select(Task))  # ensure tasks loaded
    for t in tasks:
        await async_session.delete(t)
    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={"x-candidate-token": cs.token},
    )
    assert res.status_code == 500
