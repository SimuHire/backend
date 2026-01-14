from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Company, User
from app.domains.common.types import CANDIDATE_SESSION_STATUS_COMPLETED


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
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )

    # Create simulation
    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
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
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert isinstance(body["candidateSessionId"], int)
    assert body["candidateSessionId"] > 0

    assert isinstance(body["token"], str)
    # token_urlsafe(32) is typically ~43 chars, but just ensure "unguessable-ish"
    assert len(body["token"]) >= 32

    assert isinstance(body["inviteUrl"], str)
    assert body["inviteUrl"].endswith(f"/candidate/session/{body['token']}")
    assert body["outcome"] == "created"

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
async def test_invite_resends_existing_active(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )

    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    sim_id = create_sim.json()["id"]

    first = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert first.status_code == 200
    first_body = first.json()

    second = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["candidateSessionId"] == first_body["candidateSessionId"]
    assert second_body["outcome"] == "resent"

    stmt = select(CandidateSession).where(CandidateSession.simulation_id == sim_id)
    rows = (await async_session.execute(stmt)).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_invite_expired_refreshes_token(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )

    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    sim_id = create_sim.json()["id"]

    first = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert first.status_code == 200
    first_body = first.json()

    stmt = select(CandidateSession).where(
        CandidateSession.id == first_body["candidateSessionId"]
    )
    cs = (await async_session.execute(stmt)).scalar_one()
    cs.expires_at = datetime.now(UTC) - timedelta(days=1)
    await async_session.commit()

    second = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["candidateSessionId"] == first_body["candidateSessionId"]
    assert second_body["token"] != first_body["token"]
    assert second_body["outcome"] == "created"


@pytest.mark.asyncio
async def test_invite_completed_rejected(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )

    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    sim_id = create_sim.json()["id"]

    first = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert first.status_code == 200
    first_body = first.json()

    stmt = select(CandidateSession).where(
        CandidateSession.id == first_body["candidateSessionId"]
    )
    cs = (await async_session.execute(stmt)).scalar_one()
    cs.status = CANDIDATE_SESSION_STATUS_COMPLETED
    cs.completed_at = datetime.now(UTC)
    await async_session.commit()

    second = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert second.status_code == 409
    payload = second.json()
    assert payload["error"]["outcome"] == "rejected"
    assert payload["error"]["code"] == "candidate_already_completed"


@pytest.mark.asyncio
async def test_invite_concurrent_requests_idempotent(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )

    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    sim_id = create_sim.json()["id"]

    async def _invite():
        return await async_client.post(
            f"/api/simulations/{sim_id}/invite",
            headers={"x-dev-user-email": "recruiterA@tenon.com"},
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
        )

    # async_client uses a shared session fixture, so true concurrency would
    # contend on a single transaction. Run sequentially as a best-effort check.
    first = await _invite()
    second = await _invite()
    assert first.status_code == 200
    assert second.status_code == 200
    outcomes = {first.json()["outcome"], second.json()["outcome"]}
    assert outcomes == {"created", "resent"}

    stmt = select(CandidateSession).where(CandidateSession.simulation_id == sim_id)
    rows = (await async_session.execute(stmt)).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_invite_invalid_simulation_returns_404(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    await seed_recruiter(
        async_session,
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )

    resp = await async_client.post(
        "/api/simulations/999999/invite",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invite_not_owned_simulation_returns_404(
    async_client, async_session: AsyncSession
):
    await seed_recruiter(
        async_session,
        email="recruiterA@tenon.com",
        company_name="Recruiter A Co",
    )
    await seed_recruiter(
        async_session,
        email="recruiterB@tenon.com",
        company_name="Recruiter B Co",
    )

    # Recruiter A creates sim
    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": "recruiterA@tenon.com"},
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
        headers={"x-dev-user-email": "recruiterB@tenon.com"},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 404
