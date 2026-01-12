import pytest

from app.infra.security import candidate_access
from app.infra.security.principal import Principal


@pytest.mark.asyncio
async def test_require_candidate_principal_allows_candidate():
    principal = Principal(
        sub="auth0|cand1",
        email="candidate@example.com",
        name="candidate",
        roles=[],
        permissions=["candidate:access"],
        claims={"sub": "auth0|cand1", "email": "candidate@example.com"},
    )
    result = await candidate_access.require_candidate_principal(principal)
    assert result == principal


@pytest.mark.asyncio
async def test_require_candidate_principal_rejects_missing_permission():
    principal = Principal(
        sub="auth0|recruiter1",
        email="recruiter@example.com",
        name="recruiter",
        roles=[],
        permissions=["recruiter:access"],
        claims={"sub": "auth0|recruiter1", "email": "recruiter@example.com"},
    )
    with pytest.raises(Exception) as excinfo:
        await candidate_access.require_candidate_principal(principal)
    assert excinfo.value.status_code == 403
