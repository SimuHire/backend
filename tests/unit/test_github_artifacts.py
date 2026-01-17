from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

from app.domains.github_native.actions_runner import GithubActionsRunner
from app.domains.github_native.artifacts import parse_test_results_zip
from app.domains.github_native.client import GithubClient, WorkflowRun


def test_parse_test_results_prefers_json():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr(
            "tenon-test-results.json",
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
        zf.writestr("tenon-test-results.json", '{"passed":5,"failed":1,"total":6}')
    other_buf = io.BytesIO()
    with ZipFile(other_buf, "w") as zf:
        zf.writestr("other.json", '{"passed":1,"failed":0,"total":1}')

    client = _StubClient(
        artifacts=[
            {"id": 1, "name": "unrelated"},
            {"id": 2, "name": "tenon-test-results"},
        ],
        contents={1: other_buf.getvalue(), 2: preferred_buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="ci.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 10)
    assert error is None
    assert parsed
    assert parsed.passed == 5
    assert parsed.failed == 1
    assert parsed.total == 6


async def test_parse_artifacts_skips_expired():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("tenon-test-results.json", '{"passed":2,"failed":0,"total":2}')
    client = _StubClient(
        artifacts=[{"id": 1, "name": "tenon-test-results", "expired": True}],
        contents={1: buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="ci.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 10)
    assert parsed is None
    assert error == "artifact_missing"


def test_parse_test_results_handles_malformed_json_gracefully():
    """Invalid JSON artifacts should not raise; return None instead."""
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("tenon-test-results.json", "{not-json")
    parsed = parse_test_results_zip(buf.getvalue())
    assert parsed is None


def test_parse_test_results_junit_fallback():
    """JUnit XML should be parsed when JSON artifacts are absent."""
    junit_xml = """
    <testsuite name="suite">
        <testcase classname="c" name="pass"/>
        <testcase classname="c" name="fail"><failure/></testcase>
    </testsuite>
    """
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("results.xml", junit_xml)

    parsed = parse_test_results_zip(buf.getvalue())
    assert parsed
    assert parsed.passed == 1
    assert parsed.failed == 1
    assert parsed.total == 2
    assert parsed.summary == {"format": "junit"}


async def test_parse_artifacts_handles_bad_zip_without_crashing():
    """Corrupted artifacts should be ignored instead of raising."""
    client = _StubClient(
        artifacts=[{"id": 1, "name": "tenon-test-results"}],
        contents={1: b"this-is-not-a-zip"},
    )
    runner = GithubActionsRunner(client, workflow_file="ci.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 42)
    assert parsed is None
    assert error == "artifact_corrupt"


def test_parse_test_results_json_fallback_and_bad_xml():
    """Non-preferred JSON should be parsed; invalid XML ignored."""
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("other.json", '{"passed":3,"failed":1,"total":4,"summary":{"s":1}}')
        zf.writestr("broken.xml", "<testsuite><testcase></testsuite")

    parsed = parse_test_results_zip(buf.getvalue())
    assert (
        parsed
        and parsed.passed == 3
        and parsed.total == 4
        and parsed.summary == {"s": 1}
    )


def test_parse_test_results_bad_xml_only_returns_none():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("only.xml", "<testsuite><bad")
    assert parse_test_results_zip(buf.getvalue()) is None


def test_safe_json_load_returns_none_for_non_dict():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("array.json", "[1,2,3]")
    parsed = parse_test_results_zip(buf.getvalue())
    assert parsed is None
