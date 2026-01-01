import pytest
from sqlalchemy import select

from app.api.dependencies.notifications import get_email_service
from app.domains import CandidateSession
from app.infra.notifications.email_provider import MemoryEmailProvider
from app.services.email import EmailService
from tests.factories import create_recruiter, create_simulation


@pytest.mark.asyncio
async def test_create_simulation_seeds_default_tasks(
    async_client, async_session, auth_header_factory
):
    recruiter = await create_recruiter(
        async_session, email="owner1@example.com", name="Owner One"
    )

    payload = {
        "title": "Backend Node Simulation",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Build a new API and iterate over 5 days",
    }

    res = await async_client.post(
        "/api/simulations", json=payload, headers=auth_header_factory(recruiter)
    )
    assert res.status_code == 201, res.text

    body = res.json()
    assert body["title"] == payload["title"]
    assert len(body["tasks"]) == 5
    assert [t["day_index"] for t in body["tasks"]] == [1, 2, 3, 4, 5]
    assert body["tasks"][0]["type"] == "design"


@pytest.mark.asyncio
async def test_list_simulations_scoped_to_owner(
    async_client, async_session, auth_header_factory
):
    owner = await create_recruiter(
        async_session, email="owner@example.com", name="Owner Recruiter"
    )
    other = await create_recruiter(
        async_session, email="other@example.com", name="Other Recruiter"
    )

    owned_sim, _ = await create_simulation(
        async_session, created_by=owner, title="Owner Sim"
    )
    await create_simulation(async_session, created_by=other, title="Other Sim")

    res = await async_client.get("/api/simulations", headers=auth_header_factory(owner))
    assert res.status_code == 200, res.text

    ids = {item["id"] for item in res.json()}
    assert owned_sim.id in ids
    # cross-company sim must be hidden
    assert all(item["title"] != "Other Sim" for item in res.json())


@pytest.mark.asyncio
async def test_invite_sends_email_and_tracks_status(
    async_client, async_session, auth_header_factory, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="notify@app.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")

    with override_dependencies({get_email_service: lambda: email_service}):
        res = await async_client.post(
            f"/api/simulations/{sim.id}/invite",
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
            headers=auth_header_factory(recruiter),
        )

    assert res.status_code == 201, res.text

    cs = (await async_session.execute(select(CandidateSession))).scalar_one()
    assert cs.invite_email_status == "sent"
    assert cs.invite_email_sent_at is not None
    assert len(provider.sent) == 1
    assert provider.sent[0].to == cs.invite_email

    list_res = await async_client.get(
        f"/api/simulations/{sim.id}/candidates",
        headers=auth_header_factory(recruiter),
    )
    assert list_res.status_code == 200
    body = list_res.json()[0]
    assert body["inviteEmailStatus"] == "sent"
    assert body["inviteEmailSentAt"] is not None


@pytest.mark.asyncio
async def test_invite_candidate_rejects_unowned_simulation(
    async_client, async_session, auth_header_factory
):
    owner = await create_recruiter(async_session, email="owner@example.com")
    outsider = await create_recruiter(async_session, email="outsider@example.com")
    sim, _ = await create_simulation(async_session, created_by=owner)

    res = await async_client.post(
        f"/api/simulations/{sim.id}/invite",
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
        headers=auth_header_factory(outsider),
    )
    assert res.status_code == 404
