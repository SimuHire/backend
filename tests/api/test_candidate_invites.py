import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CandidateSession, Company, User


async def seed_recruiter(
    session: AsyncSession, *, email: str, company_name: str
) -> User:
    """
    DEV_AUTH_BYPASS requires the user already exists and has a valid company_id.
    Seed a company + recruiter user.
    """
    company = Company(name=company_name)
    session.add(company)
    await session.flush()  # populate company.id

    user = User(
        name=email.split("@")[0],
        email=email,
        role="recruiter",
        company_id=company.id,
        password_hash="",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_invite_creates_candidate_session(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@simuhire.com",
        company_name="Recruiter A Co",
    )

    # Create simulation
    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@simuhire.com"},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    assert create_sim.status_code == 201
    sim_id = create_sim.json()["id"]

    # Invite candidate
    resp = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@simuhire.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 201
    body = resp.json()

    assert isinstance(body["candidateSessionId"], int)
    assert body["candidateSessionId"] > 0

    assert isinstance(body["token"], str)
    # token_urlsafe(32) is typically ~43 chars, but just ensure "unguessable-ish"
    assert len(body["token"]) >= 32

    assert isinstance(body["inviteUrl"], str)
    assert body["inviteUrl"].endswith(f"/candidate/session/{body['token']}")

    # Verify DB row
    stmt = select(CandidateSession).where(
        CandidateSession.id == body["candidateSessionId"]
    )
    cs = (await async_session.execute(stmt)).scalar_one()

    assert cs.simulation_id == sim_id
    assert cs.invite_email == "jane@example.com"
    assert cs.status == "not_started"
    assert cs.token == body["token"]

    # candidateName -> candidate_name
    assert cs.candidate_name == "Jane Doe"


@pytest.mark.asyncio
async def test_invite_invalid_simulation_returns_404(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@simuhire.com",
        company_name="Recruiter A Co",
    )

    resp = await async_client.post(
        "/api/simulations/999999/invite",
        headers={"x-dev-user-email": "recruiterA@simuhire.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invite_not_owned_simulation_returns_404(
    async_client, async_session: AsyncSession
):
    await seed_recruiter(
        async_session,
        email="recruiterA@simuhire.com",
        company_name="Recruiter A Co",
    )
    await seed_recruiter(
        async_session,
        email="recruiterB@simuhire.com",
        company_name="Recruiter B Co",
    )

    # Recruiter A creates sim
    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@simuhire.com"},
        json={
            "title": "Sim Owned By A",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Focus",
        },
    )
    assert create_sim.status_code == 201
    sim_id = create_sim.json()["id"]

    # Recruiter B attempts invite -> 404 (do not leak existence)
    resp = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterB@simuhire.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 404
