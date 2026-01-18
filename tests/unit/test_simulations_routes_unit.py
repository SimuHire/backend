from types import SimpleNamespace

import pytest

from app.api import error_utils
from app.api.routes import simulations
from app.domains.github_native.client import GithubError
from app.domains.simulations import service as sim_service
from app.infra.security import rate_limit


def _fake_request():
    return type(
        "Req",
        (),
        {"headers": {}, "client": type("c", (), {"host": "127.0.0.1"})()},
    )()


@pytest.mark.asyncio
async def test_create_candidate_invite_rejected(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: False)
    exc = sim_service.InviteRejectedError()

    async def fake_require(db, simulation_id, user_id):
        return SimpleNamespace(id=1, title="t", role="r"), []

    async def fake_create(db, simulation_id, payload, now):
        raise exc

    monkeypatch.setattr(
        sim_service, "require_owned_simulation_with_tasks", fake_require
    )
    monkeypatch.setattr(sim_service, "create_or_resend_invite", fake_create)

    response = await simulations.create_candidate_invite(
        simulation_id=1,
        payload=SimpleNamespace(inviteEmail="a@b.com", candidateName="C"),
        request=_fake_request(),
        db=None,
        user=SimpleNamespace(id=1, role="recruiter"),
        email_service=None,
        github_client=None,
    )
    assert response.status_code == 409
    assert response.body


@pytest.mark.asyncio
async def test_create_candidate_invite_github_error(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: False)

    task = SimpleNamespace(id=2, day_index=2, type="code", template_repo="owner/repo")

    async def fake_require(db, simulation_id, user_id):
        sim = SimpleNamespace(id=1, title="t", role="r")
        return sim, [task]

    async def fake_create(db, simulation_id, payload, now):
        return SimpleNamespace(id=10, token="tok"), "created"

    async def fail_workspace(
        db,
        candidate_session,
        task,
        github_client,
        github_username,
        repo_prefix,
        template_default_owner,
        now,
    ):
        raise GithubError("nope", status_code=403)

    monkeypatch.setattr(
        sim_service, "require_owned_simulation_with_tasks", fake_require
    )
    monkeypatch.setattr(sim_service, "create_or_resend_invite", fake_create)
    monkeypatch.setattr(
        simulations.submission_service, "ensure_workspace", fail_workspace
    )

    with pytest.raises(error_utils.ApiError) as excinfo:
        await simulations.create_candidate_invite(
            simulation_id=1,
            payload=SimpleNamespace(inviteEmail="a@b.com", candidateName="C"),
            request=_fake_request(),
            db=None,
            user=SimpleNamespace(id=1, role="recruiter"),
            email_service=None,
            github_client=None,
        )
    assert excinfo.value.error_code == "GITHUB_PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_resend_candidate_invite_rate_limited(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: True)
    limiter_calls = []

    class DummyLimiter:
        def allow(self, key, rule):
            limiter_calls.append(key)

    monkeypatch.setattr(rate_limit, "limiter", DummyLimiter())

    async def fake_require(db, simulation_id, user_id):
        return SimpleNamespace(id=1)

    fake_cs = SimpleNamespace(
        id=2,
        simulation_id=1,
        token="tok",
        invite_email_status=None,
        invite_email_sent_at=None,
        invite_email_error=None,
    )

    class FakeSession:
        async def get(self, model, id):
            return fake_cs

    async def fake_send(
        db, candidate_session, simulation, invite_url, email_service, now
    ):
        fake_cs.invite_email_status = "sent"
        return SimpleNamespace(status="sent")

    monkeypatch.setattr(sim_service, "require_owned_simulation", fake_require)
    monkeypatch.setattr(
        simulations.notification_service, "send_invite_email", fake_send
    )

    result = await simulations.resend_candidate_invite(
        simulation_id=1,
        candidate_session_id=2,
        request=_fake_request(),
        db=FakeSession(),
        user=SimpleNamespace(id=1, role="recruiter"),
        email_service=None,
    )
    assert result["inviteEmailStatus"] == "sent"
    assert limiter_calls


@pytest.mark.asyncio
async def test_create_candidate_invite_skips_non_code_tasks(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: False)
    calls = []

    async def fake_require(db, simulation_id, user_id):
        sim = SimpleNamespace(id=1, title="t", role="r")
        tasks = [
            SimpleNamespace(id=1, day_index=1, type="design", template_repo=None),
            SimpleNamespace(id=2, day_index=2, type="design", template_repo=None),
        ]
        return sim, tasks

    async def fake_create(db, simulation_id, payload, now):
        return SimpleNamespace(id=10, token="tok", simulation_id=1), "created"

    async def ensure_workspace(**_kwargs):
        calls.append("workspace")

    async def fake_email(*_args, **_kwargs):
        return SimpleNamespace(status="sent")

    monkeypatch.setattr(
        sim_service, "require_owned_simulation_with_tasks", fake_require
    )
    monkeypatch.setattr(sim_service, "create_or_resend_invite", fake_create)
    monkeypatch.setattr(
        simulations.submission_service, "ensure_workspace", ensure_workspace
    )
    monkeypatch.setattr(
        simulations.notification_service, "send_invite_email", fake_email
    )

    resp = await simulations.create_candidate_invite(
        simulation_id=1,
        payload=SimpleNamespace(inviteEmail="a@b.com", candidateName="C"),
        request=_fake_request(),
        db=None,
        user=SimpleNamespace(id=1, role="recruiter"),
        email_service=None,
        github_client=None,
    )
    assert resp.candidateSessionId == 10
    assert calls == []


@pytest.mark.asyncio
async def test_resend_candidate_invite_not_found(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: False)

    async def fake_require(db, simulation_id, user_id):
        return SimpleNamespace(id=1)

    class FakeSession:
        async def get(self, model, id):
            return SimpleNamespace(simulation_id=999)

    monkeypatch.setattr(sim_service, "require_owned_simulation", fake_require)

    with pytest.raises(Exception) as excinfo:
        await simulations.resend_candidate_invite(
            simulation_id=1,
            candidate_session_id=2,
            request=_fake_request(),
            db=FakeSession(),
            user=SimpleNamespace(id=1, role="recruiter"),
            email_service=None,
        )
    assert excinfo.value.status_code == 404
