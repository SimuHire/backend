import pytest

import app.core.auth.auth0 as auth0_module
from app.core.auth import dependencies as security_deps
from app.core.auth.current_user import get_current_user
from app.core.settings import settings
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


@pytest.fixture(autouse=True)
def patch_auth0_decode(monkeypatch):
    """Parse shorthand tokens like recruiter:email or candidate:email for tests."""

    def fake_decode(token: str):
        kind, email = token.split(":", 1) if ":" in token else ("candidate", token)
        perms = []
        if kind == "recruiter":
            perms = ["recruiter:access"]
        elif kind == "candidate":
            perms = ["candidate:access"]
        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
        return {
            "sub": f"{kind}|{email}",
            "email": email,
            email_claim: email,
            "permissions": perms,
            permissions_claim: perms,
        }

    monkeypatch.setattr(auth0_module, "decode_auth0_token", fake_decode)


@pytest.mark.asyncio
async def test_candidate_token_cannot_access_recruiter_routes(
    async_client, async_session, override_dependencies
):
    await create_recruiter(async_session, email="owner@test.com")
    recruiter = await create_recruiter(async_session, email="owner2@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    token = f"candidate:{cs.invite_email}"
    # Restore real dependency to enforce Auth0 permissions for this test.
    with override_dependencies({get_current_user: security_deps.get_current_user}):
        res = await async_client.get(
            "/api/simulations",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert res.status_code in {401, 403}


@pytest.mark.asyncio
async def test_recruiter_token_cannot_access_candidate_routes(
    async_client, async_session
):
    recruiter = await create_recruiter(async_session, email="recruiter@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": "Bearer recruiter:recruiter@test.com",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_invite_token_requires_auth(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="inviteauth@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    res = await async_client.get(f"/api/candidate/session/{cs.token}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_candidate_current_task_requires_auth(
    async_client, async_session, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="authcheck@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    from app.core.auth import dependencies as security_deps
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.get(
            f"/api/candidate/session/{cs.id}/current_task",
            headers={"x-candidate-session-id": str(cs.id)},
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_candidate_email_bypass_rejected(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="bypass@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    res = await async_client.get(
        f"/api/candidate/session/{cs.id}/current_task",
        headers={
            "Authorization": "Bearer candidate:bypass@example.com",
            "x-candidate-session-id": str(cs.id),
        },
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_candidate_codespace_requires_auth(
    async_client, async_session, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="auth2@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    task_id = tasks[0].id

    from app.core.auth import dependencies as security_deps
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.post(
            f"/api/tasks/{task_id}/codespace/init",
            json={"githubUsername": "octocat"},
            headers={"x-candidate-session-id": str(cs.id)},
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_candidate_run_requires_auth(
    async_client, async_session, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="auth3@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    task_id = tasks[0].id

    from app.core.auth import dependencies as security_deps
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.post(
            f"/api/tasks/{task_id}/run",
            json={"branch": None, "workflowInputs": None},
            headers={"x-candidate-session-id": str(cs.id)},
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_candidate_matching_email_can_claim(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="claim@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    token = f"candidate:{cs.invite_email}"

    res = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_candidate_mismatched_email_gets_403(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="claim403@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    other = await create_candidate_session(
        async_session, simulation=sim, invite_email="other@example.com"
    )
    token = f"candidate:{other.invite_email}"

    res = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_namespaced_permissions_only_candidate_access(
    async_client, async_session, monkeypatch, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="namespaced@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    def decode(_token: str):
        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
        return {
            "sub": "auth0|c-ns",
            email_claim: cs.invite_email,
            permissions_claim: ["candidate:access"],
        }

    monkeypatch.setattr(auth0_module, "decode_auth0_token", decode)
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.get(
            f"/api/candidate/session/{cs.token}",
            headers={"Authorization": "Bearer token"},
        )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_namespaced_permissions_allow_recruiter_route(
    async_client, monkeypatch, override_dependencies
):
    def decode(_token: str):
        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
        return {
            "sub": "auth0|r1",
            email_claim: "r@test.com",
            permissions_claim: ["recruiter:access"],
        }

    monkeypatch.setattr(auth0_module, "decode_auth0_token", decode)
    with override_dependencies({get_current_user: security_deps.get_current_user}):
        res = await async_client.get(
            "/api/simulations",
            headers={"Authorization": "Bearer token"},
        )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_roles_mapping_allows_candidate_route(
    async_client, async_session, monkeypatch, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="rolemap@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    def decode(_token: str):
        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        roles_claim = settings.auth.AUTH0_ROLES_CLAIM
        return {
            "sub": "auth0|c1",
            email_claim: cs.invite_email,
            roles_claim: ["candidate-basic"],
        }

    monkeypatch.setattr(auth0_module, "decode_auth0_token", decode)
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.get(
            f"/api/candidate/session/{cs.token}",
            headers={"Authorization": "Bearer token"},
        )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_missing_permissions_and_roles_returns_403(
    async_client, async_session, monkeypatch, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="noperms@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    def decode(_token: str):
        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        return {
            "sub": "auth0|c2",
            email_claim: cs.invite_email,
        }

    monkeypatch.setattr(auth0_module, "decode_auth0_token", decode)
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.get(
            f"/api/candidate/session/{cs.token}",
            headers={"Authorization": "Bearer token"},
        )
    assert res.status_code == 403
