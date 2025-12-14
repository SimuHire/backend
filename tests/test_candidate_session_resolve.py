from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.candidate_session import CandidateSession
from app.models.company import Company
from app.models.submission import Submission
from app.models.task import Task
from app.models.user import User

# -------------------------
# Shared helpers (mirrors resolve tests)
# -------------------------


async def _seed_recruiter(
    async_session, email: str = "recruiter1@simuhire.com"
) -> User:
    company = Company(name="TestCo")
    async_session.add(company)
    await async_session.commit()
    await async_session.refresh(company)

    user = User(
        name="Recruiter One",
        email=email,
        role="recruiter",
        company_id=company.id,
        password_hash="",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _create_simulation(async_client, recruiter_email: str) -> int:
    payload = {
        "title": "Backend Node Simulation",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Build new API feature and debug an issue",
    }
    res = await async_client.post(
        "/api/simulations",
        json=payload,
        headers={"x-dev-user-email": recruiter_email},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


async def _invite_candidate(async_client, sim_id: int, recruiter_email: str) -> dict:
    payload = {"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"}
    res = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        json=payload,
        headers={"x-dev-user-email": recruiter_email},
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _resolve(async_client, token: str):
    res = await async_client.get(f"/api/candidate/session/{token}")
    assert res.status_code == 200, res.text
    return res.json()


# -------------------------
# Tests
# -------------------------


@pytest.mark.asyncio
async def test_current_task_initial_is_day_1(async_client, async_session):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    # Resolve once to start session
    await _resolve(async_client, token)

    res = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={"x-candidate-token": token},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["candidateSessionId"] == cs_id
    assert body["isComplete"] is False
    assert body["currentDayIndex"] == 1
    assert body["currentTask"]["dayIndex"] == 1
    assert body["progress"]["completed"] == 0
    assert body["progress"]["total"] == 5
    assert body["currentTask"]["description"]


@pytest.mark.asyncio
async def test_current_task_advances_after_submission(async_client, async_session):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    await _resolve(async_client, token)

    # Fetch Day 1 task
    day1_task = (
        await async_session.execute(
            select(Task).where(Task.simulation_id == sim_id, Task.day_index == 1)
        )
    ).scalar_one()

    # Insert submission for Day 1
    submission = Submission(
        candidate_session_id=cs_id,
        task_id=day1_task.id,
        submitted_at=datetime.now(UTC),
        content_text="My design solution",
    )
    async_session.add(submission)
    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={"x-candidate-token": token},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["currentDayIndex"] == 2
    assert body["progress"]["completed"] == 1
    assert body["currentTask"]["dayIndex"] == 2


@pytest.mark.asyncio
async def test_current_task_completed_after_all_tasks(async_client, async_session):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    await _resolve(async_client, token)

    tasks = (
        (await async_session.execute(select(Task).where(Task.simulation_id == sim_id)))
        .scalars()
        .all()
    )

    now = datetime.now(UTC)

    for task in tasks:
        async_session.add(
            Submission(
                candidate_session_id=cs_id,
                task_id=task.id,
                submitted_at=now,
                content_text="done",
            )
        )

    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={"x-candidate-token": token},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["isComplete"] is True
    assert body["currentTask"] is None
    assert body["currentDayIndex"] is None

    # DB state updated
    cs = (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == cs_id)
        )
    ).scalar_one()

    assert cs.status == "completed"
    assert cs.completed_at is not None


@pytest.mark.asyncio
async def test_current_task_wrong_token_404(async_client, async_session):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    await _resolve(async_client, token)

    res = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={"x-candidate-token": "wrong-token"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_current_task_expired_token_410(async_client, async_session):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    await _resolve(async_client, token)

    cs = (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == cs_id)
        )
    ).scalar_one()

    cs.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={"x-candidate-token": token},
    )
    assert res.status_code == 410
    assert res.json()["detail"] == "Invite token expired"
