from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routes import submissions as recruiter_submissions


@pytest.mark.asyncio
async def test_get_submission_detail_builds_links(monkeypatch):
    user = SimpleNamespace(id=7, role="recruiter")
    sub = SimpleNamespace(
        id=1,
        tests_passed=None,
        tests_failed=None,
        test_output=json.dumps(
            {"passed": 2, "failed": 1, "status": "failed", "conclusion": "failure"}
        ),
        diff_summary_json=json.dumps({"base": "main", "head": "feature"}),
        code_repo_path="org/repo",
        content_text=None,
        last_run_at=datetime.now(UTC),
        workflow_run_id="44",
        commit_sha="abc123",
        submitted_at=datetime.now(UTC),
        workflow_run_conclusion=None,
        workflow_run_status=None,
    )
    task = SimpleNamespace(
        id=2, day_index=1, type="code", title="T", prompt="P", description="D"
    )
    cs = SimpleNamespace(id=3)
    sim = SimpleNamespace(id=4)

    monkeypatch.setattr(
        recruiter_submissions, "ensure_recruiter", lambda _u: None, raising=False
    )

    async def _return_detail(*_a, **_k):
        return (sub, task, cs, sim)

    monkeypatch.setattr(
        recruiter_submissions.recruiter_sub_service,
        "fetch_detail",
        _return_detail,
    )
    monkeypatch.setattr(
        recruiter_submissions.recruiter_sub_service,
        "parse_test_output",
        lambda output: json.loads(output),
    )

    result = await recruiter_submissions.get_submission_detail(
        submission_id=sub.id, db=None, user=user
    )
    assert result.diffUrl == "https://github.com/org/repo/compare/main...feature"
    assert result.testResults and result.testResults.total == 3
    assert result.testResults.conclusion == "failure"
    assert result.workflowUrl.endswith("/runs/44")
    assert result.commitUrl.endswith("/commit/abc123")


@pytest.mark.asyncio
async def test_list_submissions_handles_bad_json(monkeypatch):
    user = SimpleNamespace(id=8)
    sub = SimpleNamespace(
        id=11,
        candidate_session_id=22,
        task_id=5,
        submitted_at=datetime.now(UTC),
        code_repo_path=None,
        workflow_run_id=None,
        commit_sha=None,
        diff_summary_json="{not-json",
    )
    task = SimpleNamespace(day_index=2, type="design")
    cs = SimpleNamespace(id=33)
    sim = SimpleNamespace(id=44)

    monkeypatch.setattr(recruiter_submissions, "ensure_recruiter", lambda _u: None)

    async def _list_rows(*_a, **_k):
        return [(sub, task, cs, sim)]

    monkeypatch.setattr(
        recruiter_submissions.recruiter_sub_service,
        "list_submissions",
        _list_rows,
    )

    result = await recruiter_submissions.list_submissions(
        db=None, user=user, candidateSessionId=None, taskId=None
    )
    assert result.items[0].diffSummary is None
    assert result.items[0].repoUrl is None


@pytest.mark.asyncio
async def test_recruiter_detail_handles_invalid_diff(monkeypatch):
    user = SimpleNamespace(id=9, role="recruiter")
    sub = SimpleNamespace(
        id=22,
        tests_passed=None,
        tests_failed=None,
        test_output="",
        diff_summary_json="{bad",
        code_repo_path=None,
        content_text="txt",
        last_run_at=None,
        workflow_run_id=None,
        commit_sha=None,
        submitted_at=datetime.now(UTC),
    )
    task = SimpleNamespace(id=3, day_index=1, type="design", title=None, prompt=None)
    cs = SimpleNamespace(id=4)
    sim = SimpleNamespace(id=5)

    async def _return_detail(*_a, **_k):
        return (sub, task, cs, sim)

    monkeypatch.setattr(recruiter_submissions, "ensure_recruiter", lambda _u: None)
    monkeypatch.setattr(
        recruiter_submissions.recruiter_sub_service, "fetch_detail", _return_detail
    )
    monkeypatch.setattr(
        recruiter_submissions.recruiter_sub_service,
        "parse_test_output",
        lambda output: output,
    )

    result = await recruiter_submissions.get_submission_detail(
        submission_id=sub.id, db=None, user=user
    )
    assert result.diffSummary is None
    assert result.diffUrl is None


@pytest.mark.asyncio
async def test_recruiter_list_builds_diff_url(monkeypatch):
    user = SimpleNamespace(id=10)
    sub = SimpleNamespace(
        id=33,
        candidate_session_id=44,
        task_id=5,
        submitted_at=datetime.now(UTC),
        code_repo_path="org/repo",
        workflow_run_id="99",
        commit_sha="sha",
        diff_summary_json=json.dumps({"base": "a", "head": "b"}),
    )
    task = SimpleNamespace(day_index=2, type="code")

    async def _list_rows(*_a, **_k):
        return [(sub, task, None, None)]

    monkeypatch.setattr(recruiter_submissions, "ensure_recruiter", lambda _u: None)
    monkeypatch.setattr(
        recruiter_submissions.recruiter_sub_service, "list_submissions", _list_rows
    )

    result = await recruiter_submissions.list_submissions(
        db=None, user=user, candidateSessionId=None, taskId=None
    )
    item = result.items[0]
    assert item.diffUrl.endswith("a...b")
    assert item.commitUrl.endswith("/commit/sha")
    assert item.workflowUrl.endswith("/runs/99")
