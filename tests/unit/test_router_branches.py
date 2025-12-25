import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.requests import Request

from app.routers import candidate, simulations, submissions, tasks
from app.schemas.candidate_session import CandidateInviteRequest
from app.schemas.submission import SubmissionCreateRequest
from app.security import auth0, current_user
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


def _request_with_headers(
    headers: dict[str, str], client: tuple[str, int] = ("127.0.0.1", 0)
) -> Request:
    raw_headers = [(k.encode(), v.encode()) for k, v in headers.items()]
    scope = {"type": "http", "headers": raw_headers, "client": client}
    return Request(scope)


@pytest.mark.asyncio
async def test_candidate_resolve_expired_direct(async_session):
    recruiter = await create_recruiter(async_session, email="expired-direct@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, expires_in_days=-1, status="not_started"
    )

    with pytest.raises(HTTPException) as exc:
        await candidate.resolve_candidate_session(cs.token, db=async_session)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_candidate_resolve_invalid_direct(async_session):
    with pytest.raises(HTTPException) as exc:
        await candidate.resolve_candidate_session("x" * 24, db=async_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_candidate_resolve_naive_expiry_converts(async_session):
    recruiter = await create_recruiter(async_session, email="naive@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="not_started"
    )
    cs.expires_at = cs.expires_at.replace(tzinfo=None)
    await async_session.commit()

    res = await candidate.resolve_candidate_session(cs.token, db=async_session)
    assert res.status == "in_progress"


@pytest.mark.asyncio
async def test_current_task_invalid_session_direct(async_session):
    with pytest.raises(HTTPException) as exc:
        await candidate.get_current_task(
            candidate_session_id=9999, x_candidate_token="tok", db=async_session
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_current_task_naive_expired(async_session):
    recruiter = await create_recruiter(async_session, email="naive-expire@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress", expires_in_days=-1
    )
    cs.expires_at = cs.expires_at.replace(tzinfo=None)
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await candidate.get_current_task(
            candidate_session_id=cs.id, x_candidate_token=cs.token, db=async_session
        )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_current_task_success_direct(async_session):
    recruiter = await create_recruiter(async_session, email="task-success@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    res = await candidate.get_current_task(
        candidate_session_id=cs.id, x_candidate_token=cs.token, db=async_session
    )
    assert res.currentDayIndex == 1
    assert res.isComplete is False
    assert res.progress.completed == 0


@pytest.mark.asyncio
async def test_current_task_marks_completed(async_session):
    recruiter = await create_recruiter(async_session, email="complete@test.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    # Seed submissions for all tasks
    for task in tasks_list:
        await create_submission(
            async_session, candidate_session=cs, task=task, content_text="done"
        )

    res = await candidate.get_current_task(
        candidate_session_id=cs.id, x_candidate_token=cs.token, db=async_session
    )
    assert res.isComplete is True
    await async_session.refresh(cs)
    assert cs.status == "completed"
    assert cs.completed_at is not None


@pytest.mark.asyncio
async def test_candidate_resolve_sets_started_at(async_session):
    recruiter = await create_recruiter(async_session, email="start@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="not_started", started_at=None
    )

    res = await candidate.resolve_candidate_session(cs.token, db=async_session)
    assert res.status == "in_progress"
    await async_session.refresh(cs)
    assert cs.started_at is not None


@pytest.mark.asyncio
async def test_tasks_submit_unknown_type_direct(async_session):
    recruiter = await create_recruiter(async_session, email="unknown-type@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    # Mutate existing task to unsupported type
    bad_task = tasks_list[0]
    bad_task.type = "behavioral"
    await async_session.commit()

    payload = SubmissionCreateRequest(contentText="unknown")
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=bad_task.id,
            payload=payload,
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_tasks_submit_success_direct(async_session):
    recruiter = await create_recruiter(async_session, email="direct-submit@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    payload = SubmissionCreateRequest(contentText="design answer")
    resp = await tasks.submit_task(
        task_id=tasks_list[0].id,
        payload=payload,
        x_candidate_token=cs.token,
        x_candidate_session_id=cs.id,
        db=async_session,
    )
    assert resp.progress.completed == 1
    assert resp.isComplete is False

    # Submit remaining tasks to trigger completion branch
    for task in tasks_list[1:]:
        if task.type in {"code", "debug"}:
            payload = SubmissionCreateRequest(codeBlob="print('x')")
        else:
            payload = SubmissionCreateRequest(contentText="followup")
        await tasks.submit_task(
            task_id=task.id,
            payload=payload,
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )

    refreshed = await candidate.get_current_task(
        candidate_session_id=cs.id, x_candidate_token=cs.token, db=async_session
    )
    assert refreshed.isComplete is True


@pytest.mark.asyncio
async def test_tasks_submit_task_not_found_direct(async_session):
    recruiter = await create_recruiter(async_session, email="notfound@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    payload = SubmissionCreateRequest(contentText="missing task")
    with pytest.raises(HTTPException) as exc:
        await tasks.submit_task(
            task_id=99999,
            payload=payload,
            x_candidate_token=cs.token,
            x_candidate_session_id=cs.id,
            db=async_session,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_simulations_create_requires_recruiter_direct(async_session):
    user = await create_recruiter(async_session, email="candidate-role@sim.com")
    user.role = "candidate"
    await async_session.commit()

    payload = {
        "title": "Nope",
        "role": "Backend",
        "techStack": "Python",
        "seniority": "Mid",
        "focus": "N/A",
    }
    with pytest.raises(HTTPException) as exc:
        await simulations.create_simulation(payload, db=async_session, user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_simulations_list_requires_recruiter_direct(async_session):
    user = await create_recruiter(async_session, email="candidate-role2@sim.com")
    user.role = "candidate"
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await simulations.list_simulations(db=async_session, user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_simulations_invite_and_list_candidates_direct(async_session):
    recruiter = await create_recruiter(async_session, email="owner-invite@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)

    invite = await simulations.create_candidate_invite(
        simulation_id=sim.id,
        payload=CandidateInviteRequest(
            candidateName="Jane", inviteEmail="jane@example.com"
        ),
        db=async_session,
        user=recruiter,
    )
    assert invite.candidateSessionId > 0

    candidates = await simulations.list_simulation_candidates(
        simulation_id=sim.id, db=async_session, user=recruiter
    )
    assert len(candidates) == 1


@pytest.mark.asyncio
async def test_simulations_invite_collision_raises(monkeypatch, async_session):
    recruiter = await create_recruiter(async_session, email="fail@sim.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)

    class StubResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class FailingSession:
        def __init__(self, simulation):
            self.simulation = simulation
            self.add_calls = 0
            self.rollback_calls = 0
            self.refresh_calls = 0

        async def execute(self, _stmt):
            return StubResult(self.simulation)

        def add(self, _obj):
            self.add_calls += 1

        async def commit(self):
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("stmt", "params", Exception("dupe"))

        async def rollback(self):
            self.rollback_calls += 1

        async def refresh(self, _obj):
            self.refresh_calls += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    stub_session = FailingSession(sim)
    monkeypatch.setattr(simulations, "get_session", lambda: stub_session)

    with pytest.raises(HTTPException) as exc:
        await simulations.create_candidate_invite(
            simulation_id=sim.id,
            payload=CandidateInviteRequest(
                candidateName="Jane", inviteEmail="jane@example.com"
            ),
            db=stub_session,
            user=recruiter,
        )
    assert exc.value.status_code == 500
    assert stub_session.rollback_calls == 3


@pytest.mark.asyncio
async def test_simulations_list_candidates_404_for_unowned(async_session):
    owner = await create_recruiter(async_session, email="owner-404@sim.com")
    other = await create_recruiter(async_session, email="other-404@sim.com")
    sim, _ = await create_simulation(async_session, created_by=owner)

    with pytest.raises(HTTPException) as exc:
        await simulations.list_simulation_candidates(
            simulation_id=sim.id, db=async_session, user=other
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_submissions_requires_recruiter_direct(async_session):
    owner = await create_recruiter(async_session, email="owner-sub@sim.com")
    sim, tasks_list = await create_simulation(async_session, created_by=owner)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    sub = await create_submission(
        async_session, candidate_session=cs, task=tasks_list[0], content_text="txt"
    )

    candidate_user = await create_recruiter(
        async_session, email="candidate-sub@sim.com"
    )
    candidate_user.role = "candidate"
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await submissions.get_submission_detail(
            submission_id=sub.id, db=async_session, user=candidate_user
        )
    assert exc.value.status_code == 403

    res = await submissions.list_submissions(
        db=async_session, user=owner, candidateSessionId=cs.id, taskId=tasks_list[0].id
    )
    assert len(res.items) == 1

    # taskId-only filter path
    res_task = await submissions.list_submissions(
        db=async_session, user=owner, taskId=tasks_list[0].id, candidateSessionId=None
    )
    assert len(res_task.items) == 1


@pytest.mark.asyncio
async def test_get_current_user_dev_email_not_found(async_session):
    req = _request_with_headers({"x-dev-user-email": "missing@example.com"})
    with pytest.raises(HTTPException) as exc:
        await current_user.get_current_user(
            request=req, credentials=None, db=async_session
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_requires_auth_when_no_dev(async_session):
    req = _request_with_headers({})
    with pytest.raises(HTTPException) as exc:
        await current_user.get_current_user(
            request=req, credentials=None, db=async_session
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_dev_bypass_non_local_env(monkeypatch, async_session):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(current_user.settings, "ENV", "prod")
    monkeypatch.setattr(current_user, "_env_name", lambda: "prod")
    req = _request_with_headers(
        {"x-dev-user-email": "dev@example.com"}, client=("127.0.0.1", 0)
    )

    with pytest.raises(RuntimeError):
        await current_user.get_current_user(
            request=req, credentials=None, db=async_session
        )


@pytest.mark.asyncio
async def test_get_current_user_dev_bypass_bad_host(monkeypatch, async_session):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(current_user.settings, "ENV", "prod")
    monkeypatch.setattr(current_user, "_env_name", lambda: "local")
    req = _request_with_headers(
        {"x-dev-user-email": "dev@example.com"}, client=("8.8.8.8", 0)
    )

    with pytest.raises(HTTPException) as exc:
        await current_user.get_current_user(
            request=req, credentials=None, db=async_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_dev_bypass_empty_email(monkeypatch, async_session):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(current_user.settings, "ENV", "prod")
    monkeypatch.setattr(current_user, "_env_name", lambda: "local")
    req = _request_with_headers({"x-dev-user-email": "   "}, client=("127.0.0.1", 0))

    with pytest.raises(HTTPException) as exc:
        await current_user.get_current_user(
            request=req, credentials=None, db=async_session
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_missing_email_claim(async_session, monkeypatch):
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")

    def fake_decode(_token: str) -> dict:
        return {}

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode)
    req = _request_with_headers({})
    with pytest.raises(HTTPException) as exc:
        await current_user.get_current_user(
            request=req, credentials=cred, db=async_session
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_current_user_decode_error(async_session, monkeypatch):
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")

    def fake_decode(_token: str):
        raise auth0.Auth0Error("Invalid")

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode)
    req = _request_with_headers({})
    with pytest.raises(auth0.Auth0Error):
        await current_user.get_current_user(
            request=req, credentials=cred, db=async_session
        )


@pytest.mark.asyncio
async def test_get_current_user_jwt_creates_user(async_session, monkeypatch):
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")

    def fake_decode(_token: str) -> dict:
        return {"email": "jwtuser@example.com", "name": "JWT User"}

    monkeypatch.setattr(auth0, "decode_auth0_token", fake_decode)
    session_maker = async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )
    monkeypatch.setattr(current_user, "async_session_maker", session_maker)
    req = _request_with_headers({})
    user = await current_user.get_current_user(
        request=req, credentials=cred, db=async_session
    )
    assert user.email == "jwtuser@example.com"
    assert user.name == "JWT User"


@pytest.mark.asyncio
async def test_get_current_user_jwt_integrity_error(monkeypatch):
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    monkeypatch.setattr(
        auth0, "decode_auth0_token", lambda _token: {"email": "collision@example.com"}
    )

    class StubResult:
        def __init__(self, user):
            self.user = user

        def scalar_one_or_none(self):
            return self.user

        def scalar_one(self):
            return self.user

    class FlakySession:
        def __init__(self):
            self.added = None
            self.rollback_called = False
            self.execute_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, _stmt):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return StubResult(None)
            return StubResult(self.added)

        def add(self, obj):
            self.added = obj

        async def commit(self):
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("stmt", "params", Exception("dupe"))

        async def rollback(self):
            self.rollback_called = True

        async def refresh(self, _obj):
            return None

    class FlakyMaker:
        def __init__(self):
            self.session = FlakySession()

        def __call__(self):
            return self

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *exc):
            return False

    maker = FlakyMaker()
    monkeypatch.setattr(current_user, "async_session_maker", maker)

    req = _request_with_headers({})
    user = await current_user.get_current_user(request=req, credentials=cred, db=None)
    assert user.email == "collision@example.com"
    assert user.name == "collision"
    assert maker.session.rollback_called is True


@pytest.mark.asyncio
async def test_get_current_user_dev_bypass_with_env(async_session, monkeypatch):
    monkeypatch.setattr(current_user.settings, "ENV", "prod")
    monkeypatch.setattr(current_user, "_env_name", lambda: "local")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")

    user = await create_recruiter(async_session, email="devbypass@example.com")

    session_maker = async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )
    monkeypatch.setattr(current_user, "async_session_maker", session_maker)

    req = _request_with_headers(
        {"x-dev-user-email": user.email}, client=("127.0.0.1", 0)
    )

    result = await current_user.get_current_user(
        request=req, credentials=None, db=async_session
    )
    assert result.email == user.email


@pytest.mark.asyncio
async def test_get_current_user_dev_local_path(async_session, monkeypatch):
    # ENV test triggers dev path
    monkeypatch.setattr(current_user.settings, "ENV", "test")
    await create_recruiter(async_session, email="local@example.com")
    req = _request_with_headers(
        {"x-dev-user-email": "local@example.com"}, client=("127.0.0.1", 0)
    )
    user = await current_user.get_current_user(
        request=req, credentials=None, db=async_session
    )
    assert user.email == "local@example.com"
