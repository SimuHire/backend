import pytest
from sqlalchemy import select

from app.models.candidate_session import CandidateSession
from app.models.company import Company
from app.models.user import User


async def _seed_recruiter(
    async_session, email: str = "recruiter1@simuhire.com"
) -> User:
    """
    Tests authenticate via x-dev-user-email and conftest override looks up the User in DB.
    So we must seed a recruiter user (and company) before calling recruiter-auth endpoints.
    """
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
    """
    Be tolerant to possible field naming differences (snake_case vs camelCase).
    """
    payload_snake = {
        "title": "Backend Node Simulation",
        "role": "Backend Engineer",
        "tech_stack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Build new API feature and debug an issue",
    }
    res = await async_client.post(
        "/api/simulations",
        json=payload_snake,
        headers={"x-dev-user-email": recruiter_email},
    )

    if res.status_code == 422:
        payload_camel = {
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        }
        res = await async_client.post(
            "/api/simulations",
            json=payload_camel,
            headers={"x-dev-user-email": recruiter_email},
        )

    assert res.status_code in (200, 201), res.text
    body = res.json()
    assert "id" in body, body
    return body["id"]


async def _invite_candidate(async_client, sim_id: int, recruiter_email: str) -> dict:
    """
    Be tolerant to possible field naming differences.
    """
    payload_camel = {"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"}
    res = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        json=payload_camel,
        headers={"x-dev-user-email": recruiter_email},
    )

    if res.status_code == 422:
        payload_snake = {
            "candidate_name": "Jane Doe",
            "invite_email": "jane@example.com",
        }
        res = await async_client.post(
            f"/api/simulations/{sim_id}/invite",
            json=payload_snake,
            headers={"x-dev-user-email": recruiter_email},
        )

    assert res.status_code == 201, res.text
    body = res.json()
    assert "token" in body and "candidateSessionId" in body, body
    return body


@pytest.mark.asyncio
async def test_resolve_valid_token_returns_metadata_and_updates_status(
    async_client, async_session
):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    # Resolve token (first access)
    res = await async_client.get(f"/api/candidate/session/{token}")
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["candidateSessionId"] == cs_id
    assert body["status"] == "in_progress"
    assert body["candidateName"] == "Jane Doe"
    assert body["startedAt"] is not None
    assert body["simulation"]["id"] == sim_id
    assert body["simulation"]["title"] == "Backend Node Simulation"
    assert body["simulation"]["role"] == "Backend Engineer"

    # Confirm DB updated
    row = (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == cs_id)
        )
    ).scalar_one()
    assert row.status == "in_progress"
    assert row.started_at is not None


@pytest.mark.asyncio
async def test_resolve_token_is_idempotent_started_at_does_not_change(
    async_client, async_session
):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]

    r1 = await async_client.get(f"/api/candidate/session/{token}")
    assert r1.status_code == 200, r1.text
    started_1 = r1.json()["startedAt"]

    r2 = await async_client.get(f"/api/candidate/session/{token}")
    assert r2.status_code == 200, r2.text
    started_2 = r2.json()["startedAt"]

    assert started_1 == started_2


@pytest.mark.asyncio
async def test_resolve_invalid_token_404(async_client):
    res = await async_client.get(
        "/api/candidate/session/this-token-does-not-exist-1234567890"
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Invalid invite token"


@pytest.mark.asyncio
async def test_resolve_completed_session_does_not_revert_status(
    async_client, async_session
):
    recruiter_email = "recruiter1@simuhire.com"
    await _seed_recruiter(async_session, recruiter_email)

    sim_id = await _create_simulation(async_client, recruiter_email)
    invite = await _invite_candidate(async_client, sim_id, recruiter_email)

    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    # Resolve once to set started_at + in_progress
    r1 = await async_client.get(f"/api/candidate/session/{token}")
    assert r1.status_code == 200, r1.text
    started_1 = r1.json()["startedAt"]

    # Force status to completed in DB
    cs = (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == cs_id)
        )
    ).scalar_one()
    cs.status = "completed"
    await async_session.commit()

    # Resolve again should keep completed and preserve startedAt
    r2 = await async_client.get(f"/api/candidate/session/{token}")
    assert r2.status_code == 200, r2.text
    body = r2.json()

    assert body["status"] == "completed"
    assert body["startedAt"] == started_1
