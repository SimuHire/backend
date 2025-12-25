import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.api.routes.candidate import sessions as candidate
from app.api.routes.candidate import submissions as tasks
from app.api.routes.recruiter import simulations, submissions
from app.core.security import current_user
from app.domain import Task
from app.domain.simulations.schemas import SimulationCreate
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_candidate_current_task_token_mismatch(async_session):
    recruiter = await create_recruiter(async_session, email="mismatch@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    with pytest.raises(HTTPException) as exc:
        await candidate.get_current_task(
            candidate_session_id=cs.id, x_candidate_token="wrong", db=async_session
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_candidate_current_task_no_tasks_guard(async_session):
    recruiter = await create_recruiter(async_session, email="notasks-guard@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    for t in tasks_list:
        await async_session.delete(t)
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await candidate.get_current_task(
            candidate_session_id=cs.id, x_candidate_token=cs.token, db=async_session
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_simulations_create_direct_path(async_session):
    user = await create_recruiter(async_session, email="create@sim.com")
    payload = SimulationCreate(
        title="Sim title",
        role="Role",
        techStack="Stack",
        seniority="Mid",
        focus="Focus",
    )
    resp = await simulations.create_simulation(payload, db=async_session, user=user)
    assert len(resp.tasks) == 5


@pytest.mark.asyncio
async def test_simulations_list_counts(async_session):
    recruiter = await create_recruiter(async_session, email="list@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    await create_submission(
        async_session, candidate_session=cs, task=tasks_list[0], content_text="done"
    )
    rows = await simulations.list_simulations(db=async_session, user=recruiter)
    assert rows[0].numCandidates == 1


@pytest.mark.asyncio
async def test_simulations_list_candidates_forbidden(async_session):
    recruiter = await create_recruiter(async_session, email="owner@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    other = await create_recruiter(async_session, email="other@sim.com")
    other.role = "candidate"
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await simulations.list_simulation_candidates(
            simulation_id=sim.id, db=async_session, user=other
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_simulations_invite_forbidden_and_not_found(async_session):
    recruiter = await create_recruiter(async_session, email="owner2@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    other = await create_recruiter(async_session, email="other2@sim.com")
    other.role = "candidate"
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await simulations.create_candidate_invite(
            simulation_id=sim.id,
            payload=simulations.CandidateInviteRequest(
                candidateName="x", inviteEmail="y@example.com"
            ),
            db=async_session,
            user=other,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await simulations.create_candidate_invite(
            simulation_id=sim.id + 999,
            payload=simulations.CandidateInviteRequest(
                candidateName="x", inviteEmail="y@example.com"
            ),
            db=async_session,
            user=recruiter,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_submissions_detail_full_payload(async_session):
    recruiter = await create_recruiter(async_session, email="detail@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    sub = await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks_list[0],
        content_text="text",
        code_blob="code",
        tests_passed=1,
        tests_failed=1,
        test_output="logs",
    )
    result = await submissions.get_submission_detail(
        submission_id=sub.id, db=async_session, user=recruiter
    )
    assert result.testResults.status == "failed"
    assert result.testResults.total == 2


@pytest.mark.asyncio
async def test_tasks_load_and_expiry_guards(async_session):
    with pytest.raises(HTTPException) as exc:
        await tasks._load_candidate_session_or_404(async_session, 1234, "tok")
    assert exc.value.status_code == 404

    recruiter = await create_recruiter(async_session, email="expiry@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
        expires_in_days=-1,
    )
    cs.expires_at = cs.expires_at.replace(tzinfo=None)
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await tasks._load_candidate_session_or_404(async_session, cs.id, cs.token)
    assert exc.value.status_code == 410

    with pytest.raises(HTTPException) as exc:
        await tasks._load_candidate_session_or_404(async_session, cs.id, "wrong")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_tasks_submit_wrong_simulation(async_session):
    recruiter = await create_recruiter(async_session, email="cross@sim.com")
    sim_a, tasks_a = await create_simulation(async_session, created_by=recruiter)
    sim_b, _ = await create_simulation(async_session, created_by=recruiter, title="B")
    cs = await create_candidate_session(
        async_session, simulation=sim_b, status="in_progress"
    )

    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=tasks_a[0].id,
            payload=tasks.SubmissionCreateRequest(contentText="nope"),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_tasks_compute_current_task_no_tasks(async_session):
    recruiter = await create_recruiter(async_session, email="notasks@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # remove tasks to trigger guard
    await async_session.execute(delete(Task).where(Task.simulation_id == sim.id))
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await tasks._compute_current_task(async_session, cs)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_tasks_submit_duplicate_and_outcomes(async_session, monkeypatch):
    recruiter = await create_recruiter(async_session, email="submit@sim.com")
    sim, task_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # seed existing submission to hit duplicate check
    await create_submission(
        async_session, candidate_session=cs, task=task_list[0], content_text="done"
    )

    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(contentText="again"),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 409

    # simulate completed flow (current_task None)
    async def no_current(*_args, **_kwargs):
        return None

    monkeypatch.setattr(tasks, "_compute_current_task", no_current)
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(contentText="any"),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_tasks_submit_out_of_order_and_validation(async_session, monkeypatch):
    recruiter = await create_recruiter(async_session, email="order@sim.com")
    sim, task_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # force out-of-order
    async def out_of_order(*_args, **_kwargs):
        return task_list[1]

    monkeypatch.setattr(tasks, "_compute_current_task", out_of_order)
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(contentText="any"),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 400

    # missing contentText for text task
    async def current_first(*_args, **_kwargs):
        return task_list[0]

    monkeypatch.setattr(tasks, "_compute_current_task", current_first)
    task_list[0].type = "design"
    await async_session.commit()
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(contentText="   "),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 400

    # missing code for code task
    task_list[0].type = "code"
    await async_session.commit()
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 400

    async def none_current(*_args, **_kwargs):
        return None

    monkeypatch.setattr(tasks, "_compute_current_task", none_current)
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(codeBlob="print('x')"),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_tasks_submit_integrity_error(monkeypatch, async_session):
    recruiter = await create_recruiter(async_session, email="integrity@sim.com")
    sim, task_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    original_commit = async_session.commit

    async def failing_commit():
        raise IntegrityError("stmt", "params", Exception("dupe"))

    async def identity_compute(*_args, **_kwargs):
        return task_list[0]

    monkeypatch.setattr(tasks, "_compute_current_task", identity_compute)
    monkeypatch.setattr(async_session, "commit", failing_commit)

    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=task_list[0].id,
            payload=tasks.SubmissionCreateRequest(contentText="x"),
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 409

    # restore for cleanup
    monkeypatch.setattr(async_session, "commit", original_commit)


def test_current_user_env_helper(monkeypatch):
    monkeypatch.setenv("ENV", "Prod")
    monkeypatch.setattr(current_user.settings, "ENV", "Prod")
    assert current_user._env_name() == "prod"


@pytest.mark.asyncio
async def test_current_user_empty_email_in_bypass(monkeypatch):
    class FirstStripTruthy(str):
        def __new__(cls):
            obj = super().__new__(cls, "Dev User")
            obj._stripped_once = False
            return obj

        def strip(self):
            if not self._stripped_once:
                self._stripped_once = True
                return self
            return ""

        def lower(self):
            return self

    req = type(
        "Req",
        (),
        {
            "headers": {"x-dev-user-email": FirstStripTruthy()},
            "client": type("c", (), {"host": "127.0.0.1"})(),
        },
    )()
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(current_user.settings, "ENV", "prod")
    monkeypatch.setattr(current_user, "_env_name", lambda: "local")

    class DummyResult:
        def scalar_one_or_none(self):
            return None

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, _stmt):
            return DummyResult()

    class DummyMaker:
        def __call__(self):
            return DummySession()

    monkeypatch.setattr(current_user, "async_session_maker", DummyMaker())

    with pytest.raises(HTTPException) as exc:
        await current_user.get_current_user(request=req, credentials=None, db=None)
    assert exc.value.status_code == 401
