import base64
import io
import zipfile
from datetime import UTC, datetime

import pytest

from app.api.dependencies.github_native import get_github_client
from app.core.settings import settings
from app.integrations.github import GithubError, WorkflowRun
from app.services.tasks.template_catalog import TEMPLATE_CATALOG


class MissingWorkflowGithubClient:
    async def get_repo(self, repo_full_name: str):
        return {"default_branch": "main"}

    async def get_branch(self, repo_full_name: str, branch: str):
        return {"commit": {"sha": "abc123"}}

    async def get_file_contents(
        self, repo_full_name: str, file_path: str, *, ref: str | None = None
    ):
        raise GithubError("not found", status_code=404)


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
async def test_admin_template_health_ok(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    resp = await async_client.get(
        "/api/admin/templates/health",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert len(payload["templates"]) == len(TEMPLATE_CATALOG)
    assert all(item["ok"] is True for item in payload["templates"])


@pytest.mark.asyncio
async def test_admin_template_health_missing_workflow(
    async_client, monkeypatch, override_dependencies
):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    with override_dependencies(
        {get_github_client: lambda: MissingWorkflowGithubClient()}
    ):
        resp = await async_client.get(
            "/api/admin/templates/health",
            headers={"X-Admin-Key": "test-admin-key"},
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["templates"]
    assert payload["templates"][0]["ok"] is False
    assert "workflow_file_missing" in payload["templates"][0]["errors"]


@pytest.mark.asyncio
async def test_admin_template_health_missing_key(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    resp = await async_client.get("/api/admin/templates/health")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_template_health_wrong_key(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    resp = await async_client.get(
        "/api/admin/templates/health",
        headers={"X-Admin-Key": "wrong"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_template_health_run_live(
    async_client, monkeypatch, override_dependencies
):
    class LiveGithubClient:
        async def get_repo(self, repo_full_name: str):
            return {"default_branch": "main"}

        async def get_branch(self, repo_full_name: str, branch: str):
            return {"commit": {"sha": "abc123"}}

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
            body = '{"passed": 1, "failed": 0, "total": 1, "stdout": "", "stderr": ""}'
            return _make_zip({"tenon-test-results.json": body})

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    template_key = next(iter(TEMPLATE_CATALOG))
    payload = {"templateKeys": [template_key], "mode": "live", "timeoutSeconds": 5}
    with override_dependencies({get_github_client: lambda: LiveGithubClient()}):
        resp = await async_client.post(
            "/api/admin/templates/health/run",
            json=payload,
            headers={"X-Admin-Key": "test-admin-key"},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_admin_template_health_run_live_invalid_mode(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    template_key = next(iter(TEMPLATE_CATALOG))
    payload = {"templateKeys": [template_key], "mode": "static"}
    resp = await async_client.post(
        "/api/admin/templates/health/run",
        json=payload,
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_template_health_run_live_invalid_keys(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    payload = {"templateKeys": [], "mode": "live"}
    resp = await async_client.post(
        "/api/admin/templates/health/run",
        json=payload,
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_template_health_live_mode_rejected(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    resp = await async_client.get(
        "/api/admin/templates/health?mode=live",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_template_health_run_live_unknown_key(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    payload = {"templateKeys": ["does-not-exist"], "mode": "live"}
    resp = await async_client.post(
        "/api/admin/templates/health/run",
        json=payload,
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 422
    assert "Invalid templateKeys" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_admin_template_health_run_rejects_too_many_keys(
    async_client, monkeypatch
):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    payload = {"templateKeys": ["a", "b", "c", "d", "e", "f"], "mode": "live"}
    resp = await async_client.post(
        "/api/admin/templates/health/run",
        json=payload,
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 422
