from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.routers import candidate_sessions as candidate_routes
from app.core.settings import settings
from app.domains import Task
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

    res = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
    )
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
        headers={
            "Authorization": f"Bearer candidate:{cs.invite_email}",
            "x-candidate-session-id": str(cs.id),
        },
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
async def test_invites_list_shows_candidates_for_email(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="list@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs_match = await create_candidate_session(async_session, simulation=sim)
    await create_candidate_session(
        async_session,
        simulation=sim,
        invite_email="other@example.com",
        candidate_name="Other",
    )

    res = await async_client.get(
        "/api/candidate/invites",
        headers={"Authorization": f"Bearer candidate:{cs_match.invite_email}"},
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) == 1
    assert items[0]["candidateSessionId"] == cs_match.id


@pytest.mark.asyncio
async def test_claim_endpoint_forbidden_on_mismatch(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="claimfail@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    await create_candidate_session(
        async_session,
        simulation=sim,
        invite_email="other@example.com",
    )

    res = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": "Bearer candidate:other@example.com"},
    )
    assert res.status_code == 404


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
        headers={
            "Authorization": f"Bearer candidate:{cs.invite_email}",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_resolve_invalid_token(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="invalid@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    res = await async_client.get(
        "/api/candidate/session/" + "x" * 24,
        headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
    )
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

    res = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
    )
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_candidate_claim_rate_limited_in_prod(
    async_client, async_session, monkeypatch
):
    monkeypatch.setattr(settings, "ENV", "prod")
    candidate_routes.rate_limit.limiter.reset()
    original_rule = candidate_routes.CANDIDATE_CLAIM_RATE_LIMIT
    candidate_routes.CANDIDATE_CLAIM_RATE_LIMIT = (
        candidate_routes.rate_limit.RateLimitRule(limit=1, window_seconds=60.0)
    )

    recruiter = await create_recruiter(async_session, email="claim-rate@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    first = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
    )
    assert first.status_code == 200, first.text

    second = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
    )
    assert second.status_code == 429

    candidate_routes.CANDIDATE_CLAIM_RATE_LIMIT = original_rule
    candidate_routes.rate_limit.limiter.reset()


@pytest.mark.asyncio
async def test_current_task_token_mismatch(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="tm@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    await create_candidate_session(
        async_session,
        simulation=sim,
        invite_email="other@example.com",
    )

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": "Bearer candidate:other@example.com",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_current_task_no_tasks_returns_500(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="notasks@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
    )

    # Remove all tasks to trigger guard
    await async_session.execute(select(Task))  # ensure tasks loaded
    for t in tasks:
        await async_session.delete(t)
    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": f"Bearer candidate:{cs.invite_email}",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 500
