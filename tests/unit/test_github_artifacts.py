from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

from app.services.github.actions import GithubActionsRunner
from app.services.github.artifacts import parse_test_results_zip
from app.services.github.client import GithubClient, WorkflowRun


def test_parse_test_results_prefers_json():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr(
            "simuhire-test-results.json",
            '{"passed":2,"failed":1,"total":3,"stdout":"ok","stderr":""}',
        )
    parsed = parse_test_results_zip(buf.getvalue())
    assert parsed
    assert parsed.passed == 2
    assert parsed.failed == 1
    assert parsed.total == 3
    assert parsed.stdout == "ok"


def test_is_dispatched_run_filters_event_and_created_at():
    class DummyClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")

    runner = GithubActionsRunner(DummyClient(), workflow_file="ci.yml")
    dispatch_at = datetime.now(UTC)
    recent_run = WorkflowRun(
        id=1,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="abc",
        artifact_count=0,
        event="workflow_dispatch",
        created_at=(dispatch_at - timedelta(seconds=5)).isoformat(),
    )
    old_run = WorkflowRun(
        id=2,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="def",
        artifact_count=0,
        event="workflow_dispatch",
        created_at=(dispatch_at - timedelta(seconds=30)).isoformat(),
    )
    assert runner._is_dispatched_run(recent_run, dispatch_at) is True
    assert runner._is_dispatched_run(old_run, dispatch_at) is False


class _StubClient(GithubClient):
    def __init__(self, artifacts, contents):
        super().__init__(base_url="https://api.github.com", token="x")
        self._artifacts = artifacts
        self._contents = contents

    async def list_artifacts(self, repo_full_name: str, run_id: int):
        return self._artifacts

    async def download_artifact_zip(self, repo_full_name: str, artifact_id: int):
        return self._contents[artifact_id]


async def test_parse_artifacts_prefers_named():
    preferred_buf = io.BytesIO()
    with ZipFile(preferred_buf, "w") as zf:
        zf.writestr("simuhire-test-results.json", '{"passed":5,"failed":1,"total":6}')
    other_buf = io.BytesIO()
    with ZipFile(other_buf, "w") as zf:
        zf.writestr("other.json", '{"passed":1,"failed":0,"total":1}')

    client = _StubClient(
        artifacts=[
            {"id": 1, "name": "unrelated"},
            {"id": 2, "name": "simuhire-test-results"},
        ],
        contents={1: other_buf.getvalue(), 2: preferred_buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="ci.yml")
    parsed = await runner._parse_artifacts("org/repo", 10)
    assert parsed
    assert parsed.passed == 5
    assert parsed.failed == 1
    assert parsed.total == 6


async def test_parse_artifacts_skips_expired():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("simuhire-test-results.json", '{"passed":2,"failed":0,"total":2}')
    client = _StubClient(
        artifacts=[{"id": 1, "name": "simuhire-test-results", "expired": True}],
        contents={1: buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="ci.yml")
    parsed = await runner._parse_artifacts("org/repo", 10)
    assert parsed is None
