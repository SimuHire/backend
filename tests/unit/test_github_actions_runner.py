from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domains.github_native.actions_runner import (
    ActionsRunResult,
    GithubActionsRunner,
)
from app.domains.github_native.artifacts import ParsedTestResults
from app.domains.github_native.client import (
    GithubClient,
    GithubError,
    WorkflowRun,
)


class _StubClient(GithubClient):
    def __init__(self):
        super().__init__(base_url="https://api.github.com", token="x")
        self.dispatched = False
        self.run_calls = 0

    async def trigger_workflow_dispatch(self, *args, **kwargs):
        self.dispatched = True

    async def list_workflow_runs(
        self, repo_full_name, workflow_id_or_file, *, branch=None, per_page=5
    ):
        self.run_calls += 1
        now = datetime.now(UTC).isoformat()
        return [
            WorkflowRun(
                id=1,
                status="completed",
                conclusion="success",
                html_url="https://example.com/run/1",
                head_sha="abc123",
                artifact_count=1,
                event="workflow_dispatch",
                created_at=now,
            )
        ]

    async def get_workflow_run(self, repo_full_name, run_id):
        now = datetime.now(UTC).isoformat()
        return WorkflowRun(
            id=run_id,
            status="completed",
            conclusion="failure",
            html_url="https://example.com/run/2",
            head_sha="def456",
            artifact_count=0,
            event="workflow_dispatch",
            created_at=now,
        )

    async def list_artifacts(self, repo_full_name: str, run_id: int):
        return []


@pytest.mark.asyncio
async def test_dispatch_and_wait_returns_normalized_result(monkeypatch):
    client = _StubClient()
    runner = GithubActionsRunner(
        client,
        workflow_file="ci.yml",
        poll_interval_seconds=0.01,
        max_poll_seconds=0.1,
    )

    async def fake_parse(repo, run_id):
        return (
            ParsedTestResults(
                passed=2, failed=1, total=3, stdout="ok", stderr="", summary={"s": 1}
            ),
            None,
        )

    monkeypatch.setattr(runner, "_parse_artifacts", fake_parse)

    result = await runner.dispatch_and_wait(
        repo_full_name="org/repo", ref="main", inputs={"a": "b"}
    )

    assert client.dispatched is True
    assert result.status == "passed"
    assert result.passed == 2
    assert result.failed == 1
    assert result.total == 3
    assert result.stdout == "ok"
    assert result.raw and result.raw["summary"]["s"] == 1


@pytest.mark.asyncio
async def test_dispatch_and_wait_times_out_when_no_run(monkeypatch):
    class EmptyClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            return []

    runner = GithubActionsRunner(
        EmptyClient(),
        workflow_file="ci.yml",
        poll_interval_seconds=0.01,
        max_poll_seconds=0.05,
    )
    with pytest.raises(GithubError):
        await runner.dispatch_and_wait(repo_full_name="org/repo", ref="main")


def test_normalize_run_variants():
    client = _StubClient()
    runner = GithubActionsRunner(client, workflow_file="ci.yml")
    success = runner._normalize_run(
        WorkflowRun(
            id=1,
            status="completed",
            conclusion="success",
            html_url=None,
            head_sha="sha",
        )
    )
    assert success.status == "passed"

    failure = runner._normalize_run(
        WorkflowRun(
            id=2,
            status="completed",
            conclusion="timed_out",
            html_url=None,
            head_sha="sha",
        )
    )
    assert failure.status == "failed"
    assert failure.conclusion == "timed_out"

    running = runner._normalize_run(
        WorkflowRun(
            id=3,
            status="in_progress",
            conclusion=None,
            html_url=None,
            head_sha=None,
        ),
        running=True,
    )
    assert running.status == "running"


@pytest.mark.asyncio
async def test_dispatch_and_wait_returns_running_when_candidate_never_finishes(
    monkeypatch,
):
    class SlowClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")
            self.calls = 0

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *_a, **_k):
            self.calls += 1
            now = datetime.now(UTC).isoformat()
            return [
                WorkflowRun(
                    id=8,
                    status="queued",
                    conclusion=None,
                    html_url="https://example.com/run/8",
                    head_sha="sha8",
                    artifact_count=0,
                    event="workflow_dispatch",
                    created_at=now,
                )
            ]

    runner = GithubActionsRunner(
        SlowClient(),
        workflow_file="ci.yml",
        poll_interval_seconds=0.01,
        max_poll_seconds=0.02,
    )
    result = await runner.dispatch_and_wait(repo_full_name="org/repo", ref="main")
    assert result.status == "running"


@pytest.mark.asyncio
async def test_fetch_run_result_and_artifact_parsing_paths(monkeypatch):
    class ArtifactClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")

        async def get_workflow_run(self, *_a, **_k):
            now = datetime.now(UTC).isoformat()
            return WorkflowRun(
                id=12,
                status="completed",
                conclusion="failure",
                html_url="https://example.com/run/12",
                head_sha="sha12",
                artifact_count=1,
                event="workflow_dispatch",
                created_at=now,
            )

        async def list_artifacts(self, *_a, **_k):
            return [
                {"id": 0, "expired": True},
                {"id": None},
                {"id": 99, "name": "other"},
            ]

        async def download_artifact_zip(self, *_a, **_k):
            raise GithubError("fail")

    runner = GithubActionsRunner(ArtifactClient(), workflow_file="ci.yml")
    result = await runner.fetch_run_result(repo_full_name="org/repo", run_id=12)
    assert result.conclusion == "failure"
    assert result.raw["artifact_count"] == 1


def test_is_dispatched_run_filters_invalid_dates():
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )
    run = WorkflowRun(
        id=1,
        status="queued",
        conclusion=None,
        html_url=None,
        head_sha=None,
        event="push",
        created_at="not-a-date",
    )
    assert runner._is_dispatched_run(run, datetime.now(UTC)) is False


def test_normalize_run_timed_out_and_queued():
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )
    queued = runner._normalize_run(
        WorkflowRun(
            id=5,
            status="queued",
            conclusion=None,
            html_url=None,
            head_sha="sha",
        )
    )
    assert queued.status == "running"

    timed_out = runner._normalize_run(
        WorkflowRun(
            id=6, status="completed", conclusion=None, html_url=None, head_sha="sha6"
        ),
        timed_out=True,
    )
    assert timed_out.status == "running"
    unknown = runner._normalize_run(
        WorkflowRun(
            id=9,
            status="strange",
            conclusion=None,
            html_url=None,
            head_sha="sha9",
        )
    )
    assert unknown.status == "error"


@pytest.mark.asyncio
async def test_build_result_sets_raw_when_missing(monkeypatch):
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )

    async def _fake_parse(repo, run_id):
        return (
            ParsedTestResults(
                passed=1,
                failed=0,
                total=1,
                stdout="o",
                stderr=None,
                summary={"ok": True},
            ),
            None,
        )

    monkeypatch.setattr(runner, "_parse_artifacts", _fake_parse)

    # Force _normalize_run to omit raw so branch is covered
    def _no_raw(run, **_kw):
        return ActionsRunResult(
            status="passed",
            run_id=run.id,
            conclusion="success",
            passed=None,
            failed=None,
            total=None,
            stdout=None,
            stderr=None,
            head_sha=run.head_sha,
            html_url=run.html_url,
            raw=None,
        )

    monkeypatch.setattr(runner, "_normalize_run", _no_raw)

    # Provide a run with no artifacts to keep raw None
    run = WorkflowRun(
        id=7,
        status="completed",
        conclusion="success",
        html_url="url",
        head_sha="sha",
        artifact_count=None,
    )
    result = await runner._build_result("org/repo", run)
    assert result.raw and result.raw["summary"]["ok"] is True
    assert result.status == "passed"


@pytest.mark.asyncio
async def test_build_result_marks_error_when_artifacts_missing():
    class MissingArtifactClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")

        async def list_artifacts(self, *_a, **_k):
            return []

    runner = GithubActionsRunner(MissingArtifactClient(), workflow_file="ci.yml")
    run = WorkflowRun(
        id=101,
        status="completed",
        conclusion="success",
        html_url="https://example.com/run/101",
        head_sha="sha101",
        artifact_count=0,
        event="workflow_dispatch",
        created_at=datetime.now(UTC).isoformat(),
    )
    result = await runner._build_result("org/repo", run)
    assert result.status == "error"
    assert result.raw and result.raw.get("artifact_error") == "artifact_missing"
    assert result.stderr and "artifact" in result.stderr.lower()


def test_is_dispatched_run_invalid_created_at(monkeypatch):
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )
    run = WorkflowRun(
        id=8,
        status="queued",
        conclusion=None,
        html_url=None,
        head_sha=None,
        event="workflow_dispatch",
        created_at="bad-date",
    )
    assert runner._is_dispatched_run(run, datetime.now(UTC)) is False


def test_is_dispatched_run_defaults_false():
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )
    run = WorkflowRun(
        id=10,
        status="queued",
        conclusion=None,
        html_url=None,
        head_sha=None,
        event=None,
        created_at=None,
    )
    assert runner._is_dispatched_run(run, datetime.now(UTC)) is False
