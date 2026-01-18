from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.brand import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)


class GithubError(Exception):
    """Raised when GitHub API calls fail."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class WorkflowRun:
    """Normalized workflow run information."""

    id: int
    status: str
    conclusion: str | None
    html_url: str | None
    head_sha: str | None
    artifact_count: int | None = None
    event: str | None = None
    created_at: str | None = None


class GithubClient:
    """Minimal GitHub REST client for template + Actions workflows."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        default_org: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.default_org = default_org
        self.transport = transport
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            transport=self.transport,
        )

    async def generate_repo_from_template(
        self,
        *,
        template_full_name: str,
        new_repo_name: str,
        owner: str | None = None,
        private: bool = True,
    ) -> dict[str, Any]:
        """Create a repository from a GitHub template."""
        template_owner, template_repo = self._split_full_name(template_full_name)
        payload = {
            "owner": owner or self.default_org,
            "name": new_repo_name,
            "include_all_branches": False,
            "private": private,
        }
        path = f"/repos/{template_owner}/{template_repo}/generate"
        return await self._post_json(path, json=payload)

    async def add_collaborator(
        self, repo_full_name: str, username: str, *, permission: str = "push"
    ) -> dict[str, Any]:
        """Invite a collaborator to a repository."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/collaborators/{username}"
        return await self._put_json(path, json={"permission": permission})

    async def trigger_workflow_dispatch(
        self,
        repo_full_name: str,
        workflow_id_or_file: str,
        *,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        """Trigger a workflow_dispatch event."""
        owner, repo = self._split_full_name(repo_full_name)
        path = (
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id_or_file}/dispatches"
        )
        await self._post_json(
            path, json={"ref": ref, "inputs": inputs or {}}, expect_body=False
        )

    async def get_workflow_run(self, repo_full_name: str, run_id: int) -> WorkflowRun:
        """Fetch a workflow run."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/actions/runs/{run_id}"
        data = await self._get_json(path)
        return self._parse_run(data)

    async def list_workflow_runs(
        self,
        repo_full_name: str,
        workflow_id_or_file: str,
        *,
        branch: str | None = None,
        per_page: int = 5,
    ) -> list[WorkflowRun]:
        """List workflow runs for a workflow."""
        owner, repo = self._split_full_name(repo_full_name)
        params = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id_or_file}/runs"
        data = await self._get_json(path, params=params)
        runs = data.get("workflow_runs") or []
        return [self._parse_run(r) for r in runs]

    async def get_branch(self, repo_full_name: str, branch: str) -> dict[str, Any]:
        """Fetch branch details."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/branches/{branch}"
        return await self._get_json(path)

    async def get_repo(self, repo_full_name: str) -> dict[str, Any]:
        """Fetch repository details."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}"
        return await self._get_json(path)

    async def get_file_contents(
        self, repo_full_name: str, file_path: str, *, ref: str | None = None
    ) -> dict[str, Any]:
        """Fetch repository file contents."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/contents/{file_path}"
        params = {"ref": ref} if ref else None
        return await self._get_json(path, params=params)

    async def get_compare(
        self, repo_full_name: str, base: str, head: str
    ) -> dict[str, Any]:
        """Compare two commits and return GitHub response."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/compare/{base}...{head}"
        return await self._get_json(path)

    async def list_artifacts(
        self, repo_full_name: str, run_id: int
    ) -> list[dict[str, Any]]:
        """List artifacts for a workflow run."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
        data = await self._get_json(path)
        return data.get("artifacts") or []

    async def download_artifact_zip(
        self, repo_full_name: str, artifact_id: int
    ) -> bytes:
        """Download an artifact zip archive."""
        owner, repo = self._split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"
        return await self._get_bytes(path)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    def _parse_run(self, payload: dict[str, Any]) -> WorkflowRun:
        return WorkflowRun(
            id=int(payload.get("id") or 0),
            status=str(payload.get("status") or ""),
            conclusion=payload.get("conclusion"),
            html_url=payload.get("html_url"),
            head_sha=payload.get("head_sha"),
            artifact_count=payload.get("artifacts") or payload.get("artifacts_count"),
            event=payload.get("event"),
            created_at=payload.get("created_at"),
        )

    def _split_full_name(self, full_name: str) -> tuple[str, str]:
        if not full_name or "/" not in full_name:
            raise GithubError("Invalid repository name")
        owner, repo = full_name.split("/", 1)
        if not owner or not repo:
            raise GithubError("Invalid repository name")
        return owner, repo

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict:
        return await self._request("GET", path, params=params)

    async def _post_json(
        self,
        path: str,
        *,
        json: dict[str, Any],
        expect_body: bool = True,
    ) -> dict[str, Any]:
        return await self._request("POST", path, json=json, expect_body=expect_body)

    async def _put_json(
        self, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("PUT", path, json=json)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        expect_body: bool = True,
    ) -> dict[str, Any]:
        request_url = f"{self.base_url}{path}"
        try:
            resp = await self._client.request(
                method,
                path,
                params=params,
                json=json,
            )
        except httpx.HTTPError as exc:  # pragma: no cover - network
            logger.error(
                f"github_request_failed {exc}",
                extra={"url": request_url, "error": str(exc)},
            )
            raise GithubError("GitHub request failed") from exc

        _raise_for_status(str(resp.url), resp)

        if not expect_body:
            return {}

        if "application/zip" in resp.headers.get("Content-Type", ""):
            return resp.content  # type: ignore[return-value]

        try:
            return resp.json()
        except ValueError as exc:
            raise GithubError("Invalid GitHub response") from exc

    async def _get_bytes(
        self, path: str, params: dict[str, Any] | None = None
    ) -> bytes:
        try:
            resp = await self._client.get(
                path,
                params=params,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:  # pragma: no cover - network
            logger.error(
                f"github_request_failed {exc}",
                extra={"url": f"{self.base_url}{path}", "error": str(exc)},
            )
            raise GithubError("GitHub request failed") from exc

        _raise_for_status(str(resp.url), resp)
        return resp.content


def _raise_for_status(url: str, resp: httpx.Response) -> None:
    """Common error handler for GitHub responses."""
    if resp.status_code < 400:
        return
    logger.error(
        "github_error",
        extra={
            "url": url,
            "status_code": resp.status_code,
            "body": resp.text[:500],
        },
    )
    raise GithubError(
        f"GitHub API error ({resp.status_code}) ({url}) ({resp.text[:500]})",
        status_code=resp.status_code,
    )
