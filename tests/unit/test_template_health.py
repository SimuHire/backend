import base64
import io
import zipfile
from datetime import UTC, datetime

import pytest

from app.integrations.github import (
    GithubClient,
    GithubError,
    WorkflowRun,
    template_health,
)
from app.integrations.github.template_health import (
    _decode_contents,
    check_template_health,
    workflow_contract_errors,
)
from app.services.tasks.template_catalog import TEMPLATE_CATALOG


def test_workflow_contract_errors_ok():
    content = "\n".join(
        [
            "uses: actions/upload-artifact@v4",
            "name: tenon-test-results",
            "path: artifacts/tenon-test-results.json",
        ]
    )
    errors, checks = workflow_contract_errors(content)
    assert errors == []
    assert checks["workflowHasUploadArtifact"] is True
    assert checks["workflowHasArtifactName"] is True
    assert checks["workflowHasTestResultsJson"] is True


def test_validate_and_decode_helpers():
    assert template_health._validate_test_results_schema(
        {"passed": 1, "failed": 0, "total": 1, "stdout": "", "stderr": ""}
    )
    assert template_health._validate_test_results_schema({"passed": True}) is False
    assert (
        template_health._validate_test_results_schema(
            {"passed": 1, "failed": 0, "total": 1, "stdout": 1, "stderr": ""}
        )
        is False
    )
    assert (
        template_health._validate_test_results_schema(
            {
                "passed": 1,
                "failed": 0,
                "total": 1,
                "stdout": "",
                "stderr": "",
                "summary": "bad",
            }
        )
        is False
    )
    assert (
        template_health._decode_contents({"content": "bad", "encoding": "base64"})
        is None
    )
    assert template_health._decode_contents({"content": "plain"}) == "plain"
    assert template_health._decode_contents({}) is None
    assert template_health._decode_contents({"content": b"bytes"}) is None
    assert template_health._extract_test_results_json(b"badzip") is None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{template_health.TEST_ARTIFACT_NAMESPACE}.json", "{not json")
    assert template_health._extract_test_results_json(buf.getvalue()) is None
    errors, _ = template_health.workflow_contract_errors("missing")
    assert "workflow_missing_upload_artifact" in errors
    assert (
        template_health._classify_github_error(GithubError("x", status_code=403))
        == "github_forbidden"
    )
    run = WorkflowRun(
        id=1,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="",
        event="workflow_dispatch",
        created_at="not-a-date",
    )
    assert template_health._is_dispatched_run(run, datetime.now(UTC)) is False


class _LiveStubClient(GithubClient):
    def __init__(self, responses):
        super().__init__(base_url="https://api.github.com", token="x")
        self.responses = responses

    async def trigger_workflow_dispatch(self, *a, **k):
        if self.responses.get("dispatch_error"):
            raise self.responses["dispatch_error"]

    async def list_workflow_runs(self, *a, **k):
        if "list_error" in self.responses:
            raise self.responses["list_error"]
        return self.responses.get("runs", [])

    async def list_artifacts(self, *a, **k):
        if "artifact_error" in self.responses:
            raise self.responses["artifact_error"]
        return self.responses.get("artifacts", [])

    async def download_artifact_zip(self, *a, **k):
        if "download_error" in self.responses:
            raise self.responses["download_error"]
        return self.responses.get("zip", b"")


@pytest.mark.asyncio
async def test_run_live_check_error_paths():
    client = _LiveStubClient({"dispatch_error": GithubError("deny", status_code=403)})
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "github_forbidden" in result.errors


def test_extract_test_results_json_non_dict_payload():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{template_health.TEST_ARTIFACT_NAMESPACE}.json",
            "[]",
        )
    assert template_health._extract_test_results_json(buf.getvalue()) is None


def test_is_dispatched_run_without_created_at():
    run = WorkflowRun(
        id=2,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="",
        event="workflow_dispatch",
        created_at=None,
    )
    assert template_health._is_dispatched_run(run, datetime.now(UTC)) is False


@pytest.mark.asyncio
async def test_template_health_repo_forbidden_classified():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            raise GithubError("denied", status_code=403)

    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[next(iter(TEMPLATE_CATALOG))],
    )
    assert "github_forbidden" in response.templates[0].errors


@pytest.mark.asyncio
async def test_template_health_workflow_file_rate_limited():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(self, *args, **kwargs):
            raise GithubError("slow", status_code=429)

    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[next(iter(TEMPLATE_CATALOG))],
    )
    assert "github_rate_limited" in response.templates[0].errors


@pytest.mark.asyncio
async def test_template_health_workflow_file_unreadable_other_error():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(self, *_args, **_kwargs):
            raise GithubError("boom", status_code=500)

    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[next(iter(TEMPLATE_CATALOG))],
    )
    assert "workflow_file_unreadable" in response.templates[0].errors


@pytest.mark.asyncio
async def test_run_live_check_artifact_error_and_expired(monkeypatch):
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    completed_run = WorkflowRun(
        id=123,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="",
        event="workflow_dispatch",
        created_at=now_iso,
    )
    client = _LiveStubClient(
        {
            "runs": [completed_run],
            "artifact_error": GithubError("rate", status_code=429),
        }
    )
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "github_rate_limited" in result.errors

    client = _LiveStubClient(
        {
            "runs": [completed_run],
            "artifacts": [
                {
                    "name": template_health.TEST_ARTIFACT_NAMESPACE,
                    "id": 1,
                    "expired": True,
                }
            ],
        }
    )
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "artifact_missing" in result.errors

    client = _LiveStubClient({"list_error": GithubError("rate", status_code=429)})
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "github_rate_limited" in result.errors

    client = _LiveStubClient({"runs": []})
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=0,
    )
    assert "workflow_run_timeout" in result.errors

    client = _LiveStubClient(
        {
            "runs": [completed_run],
            "artifacts": [
                {"name": template_health.LEGACY_ARTIFACT_NAME, "expired": False}
            ],
        }
    )
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "artifact_legacy_name_simuhire" in result.errors


def test_workflow_contract_errors_missing_json():
    content = "\n".join(
        [
            "uses: actions/upload-artifact@v4",
            "name: tenon-test-results",
            "path: artifacts/results.txt",
        ]
    )
    errors, checks = workflow_contract_errors(content)
    assert "workflow_missing_test_results_json" in errors
    assert checks["workflowHasUploadArtifact"] is True
    assert checks["workflowHasArtifactName"] is True
    assert checks["workflowHasTestResultsJson"] is False


def test_decode_contents_base64_with_newlines():
    content = "workflow: test"
    encoded = base64.encodebytes(content.encode("utf-8")).decode("ascii")
    payload = {"content": encoded, "encoding": "base64"}
    assert _decode_contents(payload) == content


@pytest.mark.asyncio
async def test_template_health_repo_not_found():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            raise GithubError("missing", status_code=404)

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[template_key],
    )
    item = response.templates[0]
    assert item.ok is False
    assert "repo_not_found" in item.errors


@pytest.mark.asyncio
async def test_template_health_default_branch_missing():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": ""}

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[template_key],
    )
    item = response.templates[0]
    assert item.ok is False
    assert "default_branch_missing" in item.errors


@pytest.mark.asyncio
async def test_template_health_default_branch_unusable():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            raise GithubError("bad branch")

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return {"content": "ZmlsZQ==", "encoding": "base64"}

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[template_key],
    )
    item = response.templates[0]
    assert item.ok is False
    assert "default_branch_unusable" in item.errors


@pytest.mark.asyncio
async def test_template_health_workflow_file_unreadable():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return {"content": "!!!", "encoding": "base64"}

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[template_key],
    )
    item = response.templates[0]
    assert item.ok is False
    assert "workflow_file_unreadable" in item.errors


@pytest.mark.asyncio
async def test_template_health_workflow_file_with_newlines():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            content = "\n".join(
                [
                    "uses: actions/upload-artifact@v4",
                    "name: tenon-test-results",
                    "path: artifacts/tenon-test-results.json",
                ]
            )
            encoded = base64.encodebytes(content.encode("utf-8")).decode("ascii")
            return {"content": encoded, "encoding": "base64"}

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[template_key],
    )
    item = response.templates[0]
    assert item.checks.workflowFileExists is True
    assert "workflow_file_unreadable" not in item.errors


def _make_zip(contents: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in contents.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _workflow_file_contents() -> dict[str, str]:
    content = "\n".join(
        [
            "uses: actions/upload-artifact@v4",
            "name: tenon-test-results",
            "path: artifacts/tenon-test-results.json",
        ]
    )
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return {"content": encoded, "encoding": "base64"}


def _completed_run() -> WorkflowRun:
    return WorkflowRun(
        id=42,
        status="completed",
        conclusion="success",
        html_url="https://example.com/run/42",
        head_sha="abc123",
        event="workflow_dispatch",
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


@pytest.mark.asyncio
async def test_live_health_artifact_missing():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            return [_completed_run()]

        async def list_artifacts(self, *args, **kwargs):
            return []

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert "artifact_missing" in item.errors


@pytest.mark.asyncio
async def test_live_health_legacy_artifact_name():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            return [_completed_run()]

        async def list_artifacts(self, *args, **kwargs):
            return [{"id": 1, "name": "simuhire-test-results", "expired": False}]

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert "artifact_legacy_name_simuhire" in item.errors


@pytest.mark.asyncio
async def test_live_health_zip_missing_test_results_json():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            return [_completed_run()]

        async def list_artifacts(self, *args, **kwargs):
            return [{"id": 1, "name": "tenon-test-results", "expired": False}]

        async def download_artifact_zip(self, *args, **kwargs):
            return _make_zip({"other.json": "{}"})

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert "artifact_zip_missing_test_results_json" in item.errors


@pytest.mark.asyncio
async def test_live_health_invalid_schema():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            return [_completed_run()]

        async def list_artifacts(self, *args, **kwargs):
            return [{"id": 1, "name": "tenon-test-results", "expired": False}]

        async def download_artifact_zip(self, *args, **kwargs):
            body = (
                '{"passed": "3", "failed": 0, "total": 3, "stdout": "", "stderr": ""}'
            )
            return _make_zip({"tenon-test-results.json": body})

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert "test_results_json_invalid_schema" in item.errors


@pytest.mark.asyncio
async def test_live_health_legacy_and_tenon_artifacts_prefers_tenon():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            return [_completed_run()]

        async def list_artifacts(self, *args, **kwargs):
            return [
                {"id": 1, "name": "simuhire-test-results", "expired": False},
                {"id": 2, "name": "tenon-test-results", "expired": False},
            ]

        async def download_artifact_zip(self, *args, **kwargs):
            body = '{"passed": 1, "failed": 0, "total": 1, "stdout": "", "stderr": ""}'
            return _make_zip({"tenon-test-results.json": body})

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert item.ok is True
    assert "artifact_legacy_name_simuhire" not in item.errors


@pytest.mark.asyncio
async def test_live_health_non_success_conclusion_marks_error():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            run = _completed_run()
            run.conclusion = "failure"
            return [run]

        async def list_artifacts(self, *args, **kwargs):
            return [{"id": 1, "name": "tenon-test-results", "expired": False}]

        async def download_artifact_zip(self, *args, **kwargs):
            body = '{"passed": 1, "failed": 0, "total": 1, "stdout": "", "stderr": ""}'
            return _make_zip({"tenon-test-results.json": body})

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert "workflow_run_not_success" in item.errors
    assert item.ok is False


@pytest.mark.asyncio
async def test_live_health_timed_out_conclusion_marks_error():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            run = _completed_run()
            run.conclusion = "timed_out"
            return [run]

        async def list_artifacts(self, *args, **kwargs):
            return [{"id": 1, "name": "tenon-test-results", "expired": False}]

        async def download_artifact_zip(self, *args, **kwargs):
            body = '{"passed": 1, "failed": 0, "total": 1, "stdout": "", "stderr": ""}'
            return _make_zip({"tenon-test-results.json": body})

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=5,
    )
    item = response.templates[0]
    assert "workflow_run_not_success" in item.errors
    assert item.ok is False


@pytest.mark.asyncio
async def test_live_health_ignores_non_dispatch_event():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc"}}

        async def get_file_contents(
            self, repo_full_name: str, file_path: str, *, ref: str | None = None
        ):
            return _workflow_file_contents()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            return None

        async def list_workflow_runs(self, *args, **kwargs):
            run = _completed_run()
            run.event = "push"
            return [run]

    template_key = next(iter(TEMPLATE_CATALOG))
    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="live",
        template_keys=[template_key],
        timeout_seconds=1,
    )
    item = response.templates[0]
    assert "workflow_run_timeout" in item.errors


@pytest.mark.asyncio
async def test_template_health_repo_unreachable():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            raise GithubError("oops")

    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[next(iter(TEMPLATE_CATALOG))],
    )
    assert response.templates[0].errors == ["repo_unreachable"]


@pytest.mark.asyncio
async def test_run_live_check_uncategorized_errors_and_missing_artifacts():
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    completed_run = WorkflowRun(
        id=99,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="",
        event="workflow_dispatch",
        created_at=now_iso,
    )
    client = _LiveStubClient({"list_error": GithubError("boom")})
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "workflow_dispatch_failed" in result.errors

    client = _LiveStubClient(
        {
            "runs": [completed_run],
            "artifacts": [{"name": template_health.TEST_ARTIFACT_NAMESPACE}],
        }
    )
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "artifact_missing" in result.errors

    client = _LiveStubClient(
        {
            "runs": [completed_run],
            "artifacts": [{"name": template_health.TEST_ARTIFACT_NAMESPACE, "id": 5}],
            "download_error": GithubError("nope", status_code=403),
        }
    )
    result = await template_health._run_live_check(
        client,
        repo_full_name="org/repo",
        workflow_file="wf",
        default_branch="main",
        timeout_seconds=1,
    )
    assert "github_forbidden" in result.errors
