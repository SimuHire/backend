import pytest

from tests.factories import create_recruiter


def _task_id_by_day(sim_payload: dict, day_index: int) -> int:
    for task in sim_payload["tasks"]:
        if task["day_index"] == day_index:
            return task["id"]
    raise AssertionError(f"Task with day_index={day_index} missing from payload")


@pytest.mark.asyncio
async def test_full_flow_invite_through_first_submission(
    async_client, async_session, auth_header_factory, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    recruiter = await create_recruiter(async_session, email="flow@test.com")

    sim_payload = {
        "title": "Flow Test Sim",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "End-to-end candidate flow",
    }
    sim_res = await async_client.post(
        "/api/simulations", json=sim_payload, headers=auth_header_factory(recruiter)
    )
    assert sim_res.status_code == 201, sim_res.text
    sim_body = sim_res.json()

    invite_res = await async_client.post(
        f"/api/simulations/{sim_body['id']}/invite",
        headers=auth_header_factory(recruiter),
        json={"candidateName": "Flow Candidate", "inviteEmail": "flow@example.com"},
    )
    assert invite_res.status_code == 201, invite_res.text
    invite = invite_res.json()

    verify_res = await async_client.post(
        f"/api/candidate/session/{invite['token']}/claim",
        headers={"Authorization": "Bearer candidate:flow@example.com"},
    )
    assert verify_res.status_code == 200, verify_res.text
    verify_body = verify_res.json()
    cs_id = verify_body["candidateSessionId"]
    candidate_email = "flow@example.com"

    current_res = await async_client.get(
        f"/api/candidate/session/{cs_id}/current_task",
        headers={
            "Authorization": f"Bearer candidate:{candidate_email}",
            "x-candidate-session-id": str(cs_id),
        },
    )
    assert current_res.status_code == 200, current_res.text
    assert current_res.json()["currentDayIndex"] == 1

    day1_task_id = _task_id_by_day(sim_body, 1)
    submit_res = await async_client.post(
        f"/api/tasks/{day1_task_id}/submit",
        headers={
            "Authorization": f"Bearer candidate:{candidate_email}",
            "x-candidate-session-id": str(cs_id),
        },
        json={"contentText": "Day 1 answer"},
    )
    assert submit_res.status_code == 201, submit_res.text
    submit_body = submit_res.json()
    assert submit_body["progress"]["completed"] == 1
    assert submit_body["isComplete"] is False
