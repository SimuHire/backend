from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate_session import CandidateSession
from app.models.simulation import Simulation
from app.models.submission import Submission
from app.models.task import Task
from app.models.user import User


@pytest.mark.asyncio
async def test_recruiter_can_fetch_known_submission(
    async_client, async_session: AsyncSession
):
    # Seed recruiter user (matches conftest auth)
    recruiter = User(email="recruiter1@test.com", role="recruiter")
    async_session.add(recruiter)
    await async_session.commit()
    await async_session.refresh(recruiter)

    sim = Simulation(title="Sim", role="Backend", created_by=recruiter.id)
    async_session.add(sim)
    await async_session.commit()
    await async_session.refresh(sim)

    task = Task(simulation_id=sim.id, day_index=1, type="design")
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    cs = CandidateSession(
        simulation_id=sim.id,
        invite_email="a@b.com",
        token="tok",
        candidate_name="Jane Candidate",
    )
    async_session.add(cs)
    await async_session.commit()
    await async_session.refresh(cs)

    now = datetime.now(UTC)
    sub = Submission(
        candidate_session_id=cs.id,
        task_id=task.id,
        submitted_at=now,
        content_text="my design answer",
        code_blob=None,
        code_repo_path=None,
        tests_passed=3,
        tests_failed=0,
        test_output="ok",
    )
    async_session.add(sub)
    await async_session.commit()
    await async_session.refresh(sub)

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
    recruiter1 = User(email="recruiter1@test.com", role="recruiter")
    recruiter2 = User(email="recruiter2@test.com", role="recruiter")
    async_session.add_all([recruiter1, recruiter2])
    await async_session.commit()
    await async_session.refresh(recruiter1)
    await async_session.refresh(recruiter2)

    sim = Simulation(title="Other", role="Backend", created_by=recruiter2.id)
    async_session.add(sim)
    await async_session.commit()
    await async_session.refresh(sim)

    task = Task(simulation_id=sim.id, day_index=1, type="code")
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    cs = CandidateSession(
        simulation_id=sim.id,
        invite_email="x@y.com",
        token="tok2",
        candidate_name="Other Candidate",
    )
    async_session.add(cs)
    await async_session.commit()
    await async_session.refresh(cs)

    now = datetime.now(UTC)
    sub = Submission(
        candidate_session_id=cs.id,
        task_id=task.id,
        submitted_at=now,
        content_text=None,
        code_blob="console.log('secret')",
        code_repo_path=None,
        tests_passed=None,
        tests_failed=None,
        test_output=None,
    )
    async_session.add(sub)
    await async_session.commit()
    await async_session.refresh(sub)

    resp = await async_client.get(
        f"/api/submissions/{sub.id}",
        headers={"x-dev-user-email": recruiter1.email},
    )
    # prefer 404 to avoid leaking existence
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_missing_submission_returns_404(
    async_client, async_session: AsyncSession
):
    recruiter = User(email="recruiter1@test.com", role="recruiter")
    async_session.add(recruiter)
    await async_session.commit()

    resp = await async_client.get(
        "/api/submissions/999999",
        headers={"x-dev-user-email": recruiter.email},
    )
    assert resp.status_code == 404
