import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CandidateSession, Company, Submission, User


async def seed_recruiter(
    session: AsyncSession, *, email: str, company_name: str
) -> User:
    company = Company(name=company_name)
    session.add(company)
    await session.flush()

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


async def create_simulation(async_client, recruiter_email: str) -> dict:
    resp = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": recruiter_email},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def invite_candidate(async_client, sim_id: int, recruiter_email: str) -> dict:
    resp = await async_client.post(
        f"/api/simulations/{sim_id}/invite",
        headers={"x-dev-user-email": recruiter_email},
        json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def resolve_session(async_client, token: str) -> dict:
    resp = await async_client.get(f"/api/candidate/session/{token}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_current_task(async_client, cs_id: int, token: str) -> dict:
    resp = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={"x-candidate-token": token},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def task_id_by_day(sim_json: dict, day_index: int) -> int:
    # create_simulation returns tasks with snake_case keys (day_index/type/etc)
    for t in sim_json["tasks"]:
        if t["day_index"] == day_index:
            return t["id"]
    raise AssertionError(f"Simulation missing task for day_index={day_index}")


@pytest.mark.asyncio
async def test_submit_day1_text_creates_submission_and_advances(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    sim_id = sim["id"]

    invite = await invite_candidate(async_client, sim_id, recruiter_email)
    token = invite["token"]

    resolved = await resolve_session(async_client, token)
    cs_id = resolved["candidateSessionId"]

    current = await get_current_task(async_client, cs_id, token)
    assert current["currentDayIndex"] == 1
    day1_task_id = current["currentTask"]["id"]

    submit = await async_client.post(
        f"/api/tasks/{day1_task_id}/submit",
        headers={
            "x-candidate-token": token,
            "x-candidate-session-id": str(cs_id),
        },
        json={"contentText": "Day 1 design answer"},
    )
    assert submit.status_code == 201, submit.text
    body = submit.json()
    assert body["candidateSessionId"] == cs_id
    assert body["taskId"] == day1_task_id
    assert body["progress"]["completed"] == 1

    current2 = await get_current_task(async_client, cs_id, token)
    assert current2["currentDayIndex"] == 2


@pytest.mark.asyncio
async def test_submit_day2_code_records_actions_run(
    async_client, async_session: AsyncSession, monkeypatch, actions_stubber
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    actions_stubber()

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    sim_id = sim["id"]

    invite = await invite_candidate(async_client, sim_id, recruiter_email)
    token = invite["token"]
    cs_id = (await resolve_session(async_client, token))["candidateSessionId"]

    # Submit Day 1 (text)
    day1_task_id = (await get_current_task(async_client, cs_id, token))["currentTask"][
        "id"
    ]
    r1 = await async_client.post(
        f"/api/tasks/{day1_task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={"contentText": "done"},
    )
    assert r1.status_code == 201, r1.text

    # Submit Day 2 (code)
    current2 = await get_current_task(async_client, cs_id, token)
    assert current2["currentDayIndex"] == 2
    day2_task_id = current2["currentTask"]["id"]

    # Init workspace then submit (no code payload)
    init_resp = await async_client.post(
        f"/api/tasks/{day2_task_id}/codespace/init",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={"githubUsername": "octocat"},
    )
    assert init_resp.status_code == 200, init_resp.text

    r2 = await async_client.post(
        f"/api/tasks/{day2_task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={},
    )
    assert r2.status_code == 201, r2.text

    # Verify persisted
    stmt = select(Submission).where(
        Submission.candidate_session_id == cs_id,
        Submission.task_id == day2_task_id,
    )
    sub = (await async_session.execute(stmt)).scalar_one()
    assert sub.commit_sha is not None
    assert sub.workflow_run_id is not None
    assert sub.code_repo_path is not None


@pytest.mark.asyncio
async def test_out_of_order_submission_rejected_400(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    sim_id = sim["id"]

    invite = await invite_candidate(async_client, sim_id, recruiter_email)
    token = invite["token"]
    cs_id = (await resolve_session(async_client, token))["candidateSessionId"]

    # Candidate is on day 1, but tries to submit day 3
    day3_task_id = task_id_by_day(sim, 3)

    r = await async_client.post(
        f"/api/tasks/{day3_task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={},
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_token_session_mismatch_rejected_404(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)

    invite_a = await invite_candidate(async_client, sim["id"], recruiter_email)
    token_a = invite_a["token"]
    cs_id_a = (await resolve_session(async_client, token_a))["candidateSessionId"]

    invite_b = await invite_candidate(async_client, sim["id"], recruiter_email)
    token_b = invite_b["token"]
    cs_id_b = (await resolve_session(async_client, token_b))["candidateSessionId"]

    current_b = await get_current_task(async_client, cs_id_b, token_b)
    task_id_b = current_b["currentTask"]["id"]

    # token A + session B => safe 404
    r = await async_client.post(
        f"/api/tasks/{task_id_b}/submit",
        headers={"x-candidate-token": token_a, "x-candidate-session-id": str(cs_id_b)},
        json={"contentText": "nope"},
    )
    assert r.status_code == 404, r.text

    # sanity: A can still submit its own task
    current_a = await get_current_task(async_client, cs_id_a, token_a)
    task_id_a = current_a["currentTask"]["id"]
    r_ok = await async_client.post(
        f"/api/tasks/{task_id_a}/submit",
        headers={"x-candidate-token": token_a, "x-candidate-session-id": str(cs_id_a)},
        json={"contentText": "ok"},
    )
    assert r_ok.status_code == 201, r_ok.text


@pytest.mark.asyncio
async def test_duplicate_submission_409(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    invite = await invite_candidate(async_client, sim["id"], recruiter_email)
    token = invite["token"]
    cs_id = (await resolve_session(async_client, token))["candidateSessionId"]

    current = await get_current_task(async_client, cs_id, token)
    task_id = current["currentTask"]["id"]

    r1 = await async_client.post(
        f"/api/tasks/{task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={"contentText": "first"},
    )
    assert r1.status_code == 201, r1.text

    r2 = await async_client.post(
        f"/api/tasks/{task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={"contentText": "second"},
    )
    assert r2.status_code == 409, r2.text


@pytest.mark.asyncio
async def test_text_submission_requires_content(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    invite = await invite_candidate(async_client, sim["id"], recruiter_email)
    token = invite["token"]
    cs_id = (await resolve_session(async_client, token))["candidateSessionId"]

    current = await get_current_task(async_client, cs_id, token)
    task_id = current["currentTask"]["id"]

    res = await async_client.post(
        f"/api/tasks/{task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={"contentText": "   "},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "contentText is required"


@pytest.mark.asyncio
async def test_code_submission_requires_workspace(
    async_client, async_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    invite = await invite_candidate(async_client, sim["id"], recruiter_email)
    token = invite["token"]
    cs_id = (await resolve_session(async_client, token))["candidateSessionId"]

    # Complete day 1 (text) to advance to day 2 (code)
    day1 = await get_current_task(async_client, cs_id, token)
    day1_task_id = day1["currentTask"]["id"]
    ok = await async_client.post(
        f"/api/tasks/{day1_task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={"contentText": "design answer"},
    )
    assert ok.status_code == 201, ok.text

    day2 = await get_current_task(async_client, cs_id, token)
    assert day2["currentDayIndex"] == 2
    day2_task_id = day2["currentTask"]["id"]

    res = await async_client.post(
        f"/api/tasks/{day2_task_id}/submit",
        headers={"x-candidate-token": token, "x-candidate-session-id": str(cs_id)},
        json={},
    )
    assert res.status_code == 400
    assert "Workspace not initialized" in res.json()["detail"]


@pytest.mark.asyncio
async def test_submitting_all_tasks_marks_session_complete(
    async_client, async_session: AsyncSession, monkeypatch, actions_stubber
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    actions_stubber()

    recruiter_email = "recruiterA@simuhire.com"
    await seed_recruiter(
        async_session, email=recruiter_email, company_name="Recruiter A"
    )

    sim = await create_simulation(async_client, recruiter_email)
    invite = await invite_candidate(async_client, sim["id"], recruiter_email)
    token = invite["token"]
    cs_id = (await resolve_session(async_client, token))["candidateSessionId"]

    payloads_by_day = {
        1: {"contentText": "day1 design"},
        2: {},
        3: {},
        4: {"contentText": "handoff notes"},
        5: {"contentText": "documentation"},
    }

    last_response = None
    for day_index in range(1, 6):
        current = await get_current_task(async_client, cs_id, token)
        assert current["currentDayIndex"] == day_index
        task_id = current["currentTask"]["id"]

        if current["currentTask"]["type"] in {"code", "debug"}:
            init_resp = await async_client.post(
                f"/api/tasks/{task_id}/codespace/init",
                headers={
                    "x-candidate-token": token,
                    "x-candidate-session-id": str(cs_id),
                },
                json={"githubUsername": "octocat"},
            )
            assert init_resp.status_code == 200, init_resp.text

        last_response = await async_client.post(
            f"/api/tasks/{task_id}/submit",
            headers={
                "x-candidate-token": token,
                "x-candidate-session-id": str(cs_id),
            },
            json=payloads_by_day[day_index],
        )
        assert last_response.status_code == 201, last_response.text

    assert last_response is not None
    body = last_response.json()
    assert body["isComplete"] is True
    assert body["progress"]["completed"] == 5
    assert body["progress"]["total"] == 5

    cs = (
        await async_session.execute(
            select(Submission.candidate_session_id, Submission.id)
        )
    ).scalars()
    assert len(list(cs)) == 5

    cs_row = (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == cs_id)
        )
    ).scalar_one()
    assert cs_row.status == "completed"
    assert cs_row.completed_at is not None
