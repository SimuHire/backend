from __future__ import annotations

import base64
import os
from contextlib import contextmanager

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies.github_native import get_github_client
from app.api.routes import tasks_codespaces as candidate_submissions
from app.domains import Base, User
from app.domains.github_native.actions_runner import ActionsRunResult
from app.infra.config import settings
from app.infra.db import get_session
from app.infra.security.current_user import get_current_user
from app.infra.security.principal import Principal, get_principal
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Ensure pytest-anyio uses asyncio for all async tests.
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Shared async engine for the test session (defaults to in-memory SQLite)."""
    test_url = os.getenv("TEST_DATABASE_URL") or "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(test_url, echo=False, pool_pre_ping=True, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Fresh database for each test."""
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(
        bind=db_engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )

    async with session_maker() as session:
        yield session
        # Roll back any open transaction so the connection returns cleanly.
        await session.rollback()


@pytest_asyncio.fixture(name="async_session")
async def _async_session_alias(db_session: AsyncSession) -> AsyncSession:
    """Backward-compatible alias for existing tests."""
    return db_session


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    """FastAPI TestClient wired to the shared async session + auth override."""

    class StubGithubClient:
        _workflow_text = "\n".join(
            [
                "uses: actions/upload-artifact@v4",
                "name: tenon-test-results",
                "path: artifacts/tenon-test-results.json",
            ]
        )

        async def generate_repo_from_template(
            self,
            *,
            template_full_name: str,
            new_repo_name: str,
            owner=None,
            private=True,
        ):
            return {
                "full_name": f"{owner}/{new_repo_name}",
                "id": 999,
                "default_branch": "main",
            }

        async def add_collaborator(
            self, repo_full_name: str, username: str, *, permission: str = "push"
        ):
            return {"ok": True}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "base-sha-123"}}

        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            encoded = base64.b64encode(self._workflow_text.encode("utf-8")).decode(
                "ascii"
            )
            return {"content": encoded, "encoding": "base64"}

        async def get_compare(self, repo_full_name: str, base: str, head: str):
            return {"ahead_by": 0, "behind_by": 0, "total_commits": 0, "files": []}

    async def override_get_session():
        yield db_session

    async def override_get_current_user(request: Request) -> User:
        email = (request.headers.get("x-dev-user-email") or "").strip()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing x-dev-user-email header",
            )

        result = await db_session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Dev user not found: {email}. Seed this user in the DB first.",
            )
        return user

    async def override_get_principal(request: Request) -> Principal:
        auth_header = (request.headers.get("Authorization") or "").strip()
        kind = "candidate"
        email = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            kind, email = token.split(":", 1) if ":" in token else ("candidate", token)
        else:
            # Legacy helper for existing tests: derive identity from candidate headers.
            cs_id = request.headers.get("x-candidate-session-id")
            if cs_id:
                from app.domains import CandidateSession

                cs_obj = await db_session.get(CandidateSession, int(cs_id))
                if cs_obj:
                    email = cs_obj.candidate_email or cs_obj.invite_email
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        perms: list[str] = []
        if kind == "recruiter":
            perms = ["recruiter:access"]
        elif kind == "candidate":
            perms = ["candidate:access"]
        elif kind:
            perms = [kind]

        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
        return Principal(
            sub=f"{kind}-{email}",
            email=email,
            name=email.split("@")[0],
            roles=[],
            permissions=perms,
            claims={
                "sub": f"{kind}-{email}",
                "email": email,
                email_claim: email,
                "permissions": perms,
                permissions_claim: perms,
            },
        )

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_principal] = override_get_principal
    app.dependency_overrides[get_github_client] = lambda: StubGithubClient()

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_principal, None)
    app.dependency_overrides.pop(get_github_client, None)


@pytest.fixture
def actions_stubber():
    """Fixture-scoped helper to override GitHub Actions runner + client dependencies."""

    def _apply(result: ActionsRunResult | None = None, error: Exception | None = None):
        class StubActionsRunner:
            def __init__(self, res: ActionsRunResult | None, err: Exception | None):
                self._result = res or ActionsRunResult(
                    status="passed",
                    run_id=123,
                    conclusion="success",
                    passed=1,
                    failed=0,
                    total=1,
                    stdout="ok",
                    stderr=None,
                    head_sha="abc123",
                    html_url="https://example.com/run/123",
                    raw=None,
                )
                self._error = err

            async def dispatch_and_wait(self, **_kwargs):
                if self._error:
                    raise self._error
                return self._result

            async def fetch_run_result(self, **_kwargs):
                if self._error:
                    raise self._error
                return self._result

        class StubGithubClient:
            async def generate_repo_from_template(
                self,
                *,
                template_full_name: str,
                new_repo_name: str,
                owner=None,
                private=True,
            ):
                return {
                    "full_name": f"org/{new_repo_name}",
                    "id": 999,
                    "default_branch": "main",
                }

            async def add_collaborator(
                self, repo_full_name: str, username: str, *, permission: str = "push"
            ):
                return {"ok": True}

            async def get_branch(self, repo_full_name: str, branch: str):
                return {"commit": {"sha": "base-sha-123"}}

            async def get_compare(self, repo_full_name: str, base: str, head: str):
                return {"ahead_by": 0, "behind_by": 0, "total_commits": 0, "files": []}

        runner = StubActionsRunner(result, error)
        app.dependency_overrides[candidate_submissions.get_actions_runner] = (
            lambda: runner
        )
        app.dependency_overrides[candidate_submissions.get_github_client] = (
            lambda: StubGithubClient()
        )
        return runner

    yield _apply
    app.dependency_overrides.pop(candidate_submissions.get_actions_runner, None)
    app.dependency_overrides.pop(candidate_submissions.get_github_client, None)


@pytest.fixture
def auth_header_factory():
    """Helper to build recruiter auth headers from a User."""

    def _build(user: User) -> dict[str, str]:
        return {"x-dev-user-email": user.email}

    return _build


@pytest.fixture
def candidate_header_factory():
    """Helper to build candidate headers from a session/token."""

    def _build(
        candidate_session_id: int | Base,
        token: str | None = None,
        *,
        email: str | None = None,
    ) -> dict[str, str]:
        session_id = (
            candidate_session_id.id
            if hasattr(candidate_session_id, "id")
            else candidate_session_id
        )
        if not token:
            raise ValueError("Candidate access token required for candidate headers")
        headers = {
            "x-candidate-session-id": str(session_id),
            "Authorization": f"Bearer {token}",
        }
        return headers

    return _build


@pytest.fixture
def override_dependencies():
    """Context manager to temporarily override FastAPI dependencies."""

    @contextmanager
    def _override(overrides: dict):
        app.dependency_overrides.update(overrides)
        try:
            yield
        finally:
            for dep in overrides:
                app.dependency_overrides.pop(dep, None)

    return _override
