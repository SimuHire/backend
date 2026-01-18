from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import submissions
from tests.factories import create_recruiter


def test_derive_test_status_variants():
    assert submissions._derive_test_status(None, None, None) is None
    assert submissions._derive_test_status(None, 1, "oops") == "failed"
    assert submissions._derive_test_status(2, 0, "ok") == "passed"
    assert submissions._derive_test_status(None, None, "  logs  ") == "unknown"


@pytest.mark.asyncio
async def test_get_submission_detail_not_found(async_session):
    user = await create_recruiter(async_session, email="missing-sub@sim.com")
    with pytest.raises(HTTPException) as exc:
        await submissions.get_submission_detail(
            submission_id=9999, db=async_session, user=user
        )
    assert exc.value.status_code == 404


def test_build_test_results_returns_none_when_empty():
    sub = SimpleNamespace(
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        workflow_run_id=None,
        commit_sha=None,
        last_run_at=None,
    )
    assert (
        submissions._build_test_results(
            sub,
            parsed_output=None,
            workflow_url=None,
            commit_url=None,
            include_output=True,
            max_output_chars=10,
        )
        is None
    )


def test_build_test_results_redacts_tokens_and_marks_timeout():
    sub = SimpleNamespace(
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        workflow_run_id="999",
        commit_sha="abc123",
        last_run_at=None,
    )
    parsed_output = {
        "passed": 0,
        "failed": 1,
        "total": 1,
        "stdout": "ghp_ABCDEF1234567890",
        "stderr": "github_pat_ABC1234567890",
        "conclusion": "timed_out",
    }

    result = submissions._build_test_results(
        sub,
        parsed_output,
        workflow_url="https://example.com/run/1",
        commit_url="https://example.com/commit/abc123",
        include_output=True,
        max_output_chars=9,
    )

    assert result["status"] == "failed"
    assert result["timeout"] is True
    assert result["artifactName"] == "tenon-test-results"
    assert result["stdoutTruncated"] is True
    assert result["stderrTruncated"] is True
    assert "[redacted" in (result["output"]["stdout"] or "")
    assert "[redacted" in (result["output"]["stderr"] or "")


def test_submissions_helper_redaction_and_truncate():
    assert submissions._redact_text(None) is None
    redacted = submissions._redact_text("Authorization: Bearer secret-token")
    assert "redacted" in redacted
    text, truncated = submissions._truncate_output("short", max_chars=10)
    assert text == "short" and truncated is False
    text, truncated = submissions._truncate_output("longertext", max_chars=3)
    assert text.endswith("... (truncated)") and truncated is True
    assert submissions._parse_diff_summary("{bad") is None


def test_submissions_helpers_empty_inputs_cover_branches():
    assert submissions._truncate_output(None, max_chars=5) == (None, None)
    assert submissions._build_diff_url("repo/name", {"base": None}) is None

    sub = SimpleNamespace(
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        workflow_run_id=None,
        commit_sha=None,
        last_run_at=None,
    )
    assert (
        submissions._build_test_results(
            sub,
            parsed_output={},
            workflow_url=None,
            commit_url=None,
            include_output=True,
            max_output_chars=5,
        )
        is None
    )


def test_build_test_results_uses_db_status_and_artifact_error():
    sub = SimpleNamespace(
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        workflow_run_id="77",
        commit_sha="abc123",
        last_run_at=datetime.now(UTC),
        workflow_run_status="COMPLETED",
        workflow_run_conclusion="TIMED_OUT",
    )
    parsed_output = {
        "artifactErrorCode": "MISSING",
        "stdout": "ok",
        "stderr": "err",
    }

    result = submissions._build_test_results(
        sub,
        parsed_output,
        workflow_url="https://example.com/run/77",
        commit_url="https://example.com/commit/abc123",
        include_output=False,
        max_output_chars=50,
    )

    assert result["runStatus"] == "completed"
    assert result["conclusion"] == "timed_out"
    assert result["timeout"] is False
    assert result["artifactErrorCode"] == "missing"


def test_build_test_results_sets_timeout_from_conclusion():
    sub = SimpleNamespace(
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        workflow_run_id="55",
        commit_sha=None,
        last_run_at=None,
    )
    parsed_output = {
        "passed": 0,
        "failed": 1,
        "total": 1,
        "conclusion": "timed_out",
        "stdout": "",
        "stderr": "",
    }
    result = submissions._build_test_results(
        sub,
        parsed_output,
        workflow_url=None,
        commit_url=None,
        include_output=True,
        max_output_chars=10,
    )
    assert result["timeout"] is True


def test_build_test_results_uses_db_conclusion_for_timeout():
    sub = SimpleNamespace(
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        workflow_run_id="88",
        commit_sha="c1",
        last_run_at=None,
        workflow_run_conclusion="TIMED_OUT",
    )
    result = submissions._build_test_results(
        sub,
        parsed_output=None,
        workflow_url=None,
        commit_url=None,
        include_output=False,
        max_output_chars=5,
    )
    assert result["timeout"] is True
