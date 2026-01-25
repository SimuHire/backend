from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.routes import tasks_codespaces as candidate_submissions
from app.domains.github_native.actions_runner import ActionsRunResult
from app.domains.github_native.client import GithubError
from app.domains.submissions.schemas import (
    CodespaceInitRequest,
    RunTestsRequest,
    SubmissionCreateRequest,
)
from app.infra.config import settings
from app.infra.security.principal import Principal


def _async_return(val):
    async def _inner(*_a, **_kw):
        return val

    return _inner


def _stub_cs():
    return SimpleNamespace(id=1, simulation_id=1, status="in_progress")


def _stub_task():
    return SimpleNamespace(
        id=2,
        simulation_id=1,
        type="code",
        template_repo="org/template",
        day_index=2,
        title="t",
        description="d",
    )


def _stub_workspace():
    return SimpleNamespace(
        repo_full_name="org/repo",
        default_branch="main",
        id="ws1",
        base_template_sha="base",
        last_test_summary_json=None,
        latest_commit_sha=None,
        last_workflow_run_id=None,
        last_workflow_conclusion=None,
        last_test_summary=None,
        codespace_name=None,
        codespace_url=None,
        codespace_state=None,
    )


def _principal(email: str = "candidate@example.com") -> Principal:
    email_claim = settings.auth.AUTH0_EMAIL_CLAIM
    permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
    return Principal(
        sub=f"auth0|{email}",
        email=email,
        name=email.split("@")[0],
        roles=[],
        permissions=["candidate:access"],
        claims={
            "sub": f"auth0|{email}",
            "email": email,
            email_claim: email,
            "permissions": ["candidate:access"],
            permissions_claim: ["candidate:access"],
        },
    )


@pytest.mark.asyncio
async def test_init_codespace_success_path(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    workspace.codespace_url = "https://codespaces.new/org/repo?quickstart=1"

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace(*_a, **_k):
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_workspace",
        _return_workspace,
    )

    payload = CodespaceInitRequest(githubUsername="octocat")
    result = await candidate_submissions.init_codespace(
        task_id=task.id,
        payload=payload,
        candidate_session=cs,
        db=async_session,
        github_client=object(),
    )
    assert result.repoFullName == workspace.repo_full_name
    assert result.workspaceId == workspace.id


@pytest.mark.asyncio
async def test_init_codespace_normalizes_legacy_url(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    workspace.codespace_url = "https://github.com/codespaces/new?repo=org/repo"

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace(*_a, **_k):
        return workspace

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_workspace",
        _return_workspace,
    )
    monkeypatch.setattr(async_session, "commit", _noop)
    monkeypatch.setattr(async_session, "refresh", _noop)

    payload = CodespaceInitRequest(githubUsername="octocat")
    result = await candidate_submissions.init_codespace(
        task_id=task.id,
        payload=payload,
        candidate_session=cs,
        db=async_session,
        github_client=object(),
    )
    assert result.codespaceUrl == "https://codespaces.new/org/repo?quickstart=1"
    assert workspace.codespace_url == "https://codespaces.new/org/repo?quickstart=1"


@pytest.mark.asyncio
async def test_init_codespace_missing_repo_full_name(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    workspace.repo_full_name = ""

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace(*_a, **_k):
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_workspace",
        _return_workspace,
    )

    payload = CodespaceInitRequest(githubUsername="octocat")
    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.init_codespace(
            task_id=task.id,
            payload=payload,
            candidate_session=cs,
            db=async_session,
            github_client=object(),
        )
    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_init_codespace_maps_github_error(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()

    async def _return_task(*_a, **_k):
        return task

    async def _return_current(*_a, **_k):
        return task

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )

    async def _raise_workspace(*_a, **_kw):
        raise GithubError("boom")

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_workspace",
        _raise_workspace,
    )

    payload = CodespaceInitRequest(githubUsername="octocat")
    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.init_codespace(
            task_id=task.id,
            payload=payload,
            candidate_session=cs,
            db=async_session,
            github_client=object(),
        )
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio
async def test_codespace_status_invalid_summary(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    workspace.last_test_summary_json = "{not-json"
    workspace.codespace_url = "https://codespaces.new/org/repo?quickstart=1"

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace_obj(*_a, **_kw):
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _return_workspace_obj,
    )

    resp = await candidate_submissions.codespace_status(
        task_id=task.id,
        candidate_session=cs,
        db=async_session,
    )
    assert resp.lastTestSummary is None
    assert resp.repoFullName == workspace.repo_full_name
    assert resp.codespaceUrl == "https://codespaces.new/org/repo?quickstart=1"


@pytest.mark.asyncio
async def test_codespace_status_normalizes_legacy_url(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    workspace.codespace_url = "https://github.com/codespaces/new?repo=org/repo"

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace_obj(*_a, **_kw):
        return workspace

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _return_workspace_obj,
    )
    monkeypatch.setattr(async_session, "commit", _noop)
    monkeypatch.setattr(async_session, "refresh", _noop)

    resp = await candidate_submissions.codespace_status(
        task_id=task.id,
        candidate_session=cs,
        db=async_session,
    )
    assert resp.codespaceUrl == "https://codespaces.new/org/repo?quickstart=1"
    assert workspace.codespace_url == "https://codespaces.new/org/repo?quickstart=1"


@pytest.mark.asyncio
async def test_codespace_status_missing_repo_full_name(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    workspace.repo_full_name = ""

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace_obj(*_a, **_kw):
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _return_workspace_obj,
    )

    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.codespace_status(
            task_id=task.id,
            candidate_session=cs,
            db=async_session,
        )
    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_run_task_tests_success_direct(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    result = ActionsRunResult(
        status="passed",
        run_id=9,
        conclusion="success",
        passed=1,
        failed=0,
        total=1,
        stdout="ok",
        stderr=None,
        head_sha="sha",
        html_url="https://example.com/run/9",
        raw=None,
    )

    async def _return_cs(*_a, **_k):
        return cs

    async def _return_task(*_a, **_k):
        return task

    async def _return_workspace(*_a, **_k):
        return workspace

    monkeypatch.setattr(
        candidate_submissions, "_rate_limit_or_429", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _return_workspace,
    )

    async def _return_result(**_kw):
        return result

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "run_actions_tests",
        _return_result,
    )

    async def _record_result(*_a, **_k):
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "record_run_result",
        _record_result,
    )

    resp = await candidate_submissions.run_task_tests(
        task_id=task.id,
        payload=RunTestsRequest(branch=None, workflowInputs=None),
        db=async_session,
        actions_runner=object(),
        candidate_session=cs,
    )
    assert resp.runId == 9
    assert resp.status == "passed"


@pytest.mark.asyncio
async def test_get_run_result_success_direct(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    result = ActionsRunResult(
        status="failed",
        run_id=10,
        conclusion="failure",
        passed=None,
        failed=None,
        total=None,
        stdout=None,
        stderr=None,
        head_sha="sha",
        html_url=None,
        raw=None,
    )

    _return_cs = _async_return(cs)
    _return_task = _async_return(task)
    _return_workspace_obj = _async_return(workspace)
    _record_result = _async_return(workspace)

    monkeypatch.setattr(
        candidate_submissions, "_rate_limit_or_429", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _return_workspace_obj,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "record_run_result",
        _record_result,
    )

    class Runner:
        async def fetch_run_result(self, **_kwargs):
            return result

    resp = await candidate_submissions.get_run_result(
        task_id=task.id,
        run_id=result.run_id,
        db=async_session,
        actions_runner=Runner(),
        candidate_session=cs,
    )
    assert resp.runId == 10
    assert resp.status == "failed"


@pytest.mark.asyncio
async def test_submit_task_code_path(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    result = ActionsRunResult(
        status="passed",
        run_id=11,
        conclusion="success",
        passed=1,
        failed=0,
        total=1,
        stdout="ok",
        stderr=None,
        head_sha="sha",
        html_url="https://example.com",
        raw=None,
    )

    _return_cs = _async_return(cs)
    _return_task = _async_return(task)
    _return_workspace_obj = _async_return(workspace)
    _return_result = _async_return(result)
    _record_result = _async_return(workspace)

    monkeypatch.setattr(
        candidate_submissions, "_rate_limit_or_429", lambda *_a, **_k: None
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_not_duplicate",
        _async_return(None),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_submission_payload",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "workspace_repo",
        SimpleNamespace(
            get_by_session_and_task=_return_workspace_obj,
        ),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_branch",
        lambda branch: branch,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "run_actions_tests",
        _return_result,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "record_run_result",
        _record_result,
    )

    class StubGithubClient:
        async def get_compare(self, repo_full_name, base, head):
            return {"files": []}

    async def fake_create_submission(db, candidate_session, task, payload, **_kw):
        return SimpleNamespace(
            id=99,
            task_id=task.id,
            candidate_session_id=candidate_session.id,
            submitted_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "create_submission",
        fake_create_submission,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "progress_after_submission",
        _async_return((1, 5, False)),
    )

    resp = await candidate_submissions.submit_task(
        task_id=task.id,
        payload=SubmissionCreateRequest(contentText=None),
        candidate_session=cs,
        db=async_session,
        github_client=StubGithubClient(),
        actions_runner=object(),
    )
    assert resp.submissionId == 99
    assert resp.progress.completed == 1


def test_rate_limit_or_429_enforces_in_prod(monkeypatch):
    monkeypatch.setattr(candidate_submissions.settings, "ENV", "prod")
    monkeypatch.setattr(
        candidate_submissions,
        "_RATE_LIMIT_RULE",
        {
            "init": candidate_submissions.rate_limit.RateLimitRule(
                limit=1, window_seconds=999.0
            )
        },
    )
    candidate_submissions.rate_limit.limiter.reset()
    candidate_submissions._rate_limit_or_429(1, "init")
    with pytest.raises(HTTPException):
        candidate_submissions._rate_limit_or_429(1, "init")


@pytest.mark.asyncio
async def test_compute_current_task_returns_current(monkeypatch, async_session):
    cs = _stub_cs()
    current = _stub_task()

    async def _fake_snapshot(db, _cs):
        return ([], set(), current, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _fake_snapshot
    )
    assert (
        await candidate_submissions._compute_current_task(async_session, cs) is current
    )


@pytest.mark.asyncio
async def test_codespace_status_raises_when_workspace_missing(
    monkeypatch, async_session
):
    cs = _stub_cs()
    task = _stub_task()
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _async_return(None),
    )
    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.codespace_status(
            task_id=task.id,
            candidate_session=cs,
            db=async_session,
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_run_task_tests_requires_headers(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await candidate_session_from_headers(
            principal=_principal(), x_candidate_session_id=None, db=async_session
        )
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_headers_accept_missing_candidate_token(monkeypatch, async_session):
    cs = _stub_cs()

    async def _return_session(db, session_id, principal, now):
        assert session_id == cs.id
        return cs

    monkeypatch.setattr(
        "app.api.dependencies.candidate_sessions.cs_service.fetch_owned_session",
        _return_session,
    )

    result = await candidate_session_from_headers(
        principal=_principal(),
        x_candidate_session_id=cs.id,
        db=async_session,
    )
    assert result == cs


@pytest.mark.asyncio
async def test_run_task_tests_workspace_missing(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _async_return(None),
    )
    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.run_task_tests(
            task_id=task.id,
            payload=RunTestsRequest(branch=None, workflowInputs=None),
            db=async_session,
            actions_runner=object(),
            candidate_session=cs,
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_run_task_tests_github_error(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _async_return(workspace),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_branch",
        lambda branch: branch,
    )

    class Runner:
        async def dispatch_and_wait(self, **_kwargs):
            raise GithubError("nope")

    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.run_task_tests(
            task_id=task.id,
            payload=RunTestsRequest(branch="main", workflowInputs=None),
            db=async_session,
            actions_runner=Runner(),
            candidate_session=cs,
        )
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio
async def test_get_run_result_workspace_missing(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _async_return(None),
    )
    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.get_run_result(
            task_id=task.id,
            run_id=1,
            db=async_session,
            actions_runner=object(),
            candidate_session=cs,
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_get_run_result_github_error(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.workspace_repo,
        "get_by_session_and_task",
        _async_return(workspace),
    )

    class Runner:
        async def fetch_run_result(self, **_kw):
            raise GithubError("fail")

    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.get_run_result(
            task_id=task.id,
            run_id=123,
            db=async_session,
            actions_runner=Runner(),
            candidate_session=cs,
        )
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio
async def test_submit_task_missing_workspace(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_not_duplicate",
        _async_return(None),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *_a, **_k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_submission_payload",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "is_code_task",
        lambda _task: True,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "workspace_repo",
        SimpleNamespace(get_by_session_and_task=_async_return(None)),
    )

    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.submit_task(
            task_id=task.id,
            payload=SubmissionCreateRequest(contentText=None),
            candidate_session=cs,
            db=async_session,
            github_client=object(),
            actions_runner=object(),
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_get_run_result_missing_headers(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await candidate_session_from_headers(
            principal=_principal(), x_candidate_session_id=None, db=async_session
        )
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_submit_task_github_error(monkeypatch, async_session):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_not_duplicate",
        _async_return(None),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_submission_payload",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "is_code_task",
        lambda _task: True,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "workspace_repo",
        SimpleNamespace(get_by_session_and_task=_async_return(workspace)),
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_branch",
        lambda branch: branch,
    )

    class Runner:
        async def dispatch_and_wait(self, **_kw):
            raise GithubError("fail")

    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.submit_task(
            task_id=task.id,
            payload=SubmissionCreateRequest(contentText=None),
            candidate_session=cs,
            db=async_session,
            github_client=object(),
            actions_runner=Runner(),
        )
    assert excinfo.value.status_code == 502
