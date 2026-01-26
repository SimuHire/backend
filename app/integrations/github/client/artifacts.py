from __future__ import annotations

from .names import split_full_name
from .transport import GithubTransport


class ArtifactOperations:
    transport: GithubTransport

    async def list_artifacts(self, repo_full_name: str, run_id: int) -> list[dict]:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
        data = await self._get_json(path)
        return data.get("artifacts") or []

    async def download_artifact_zip(
        self, repo_full_name: str, artifact_id: int
    ) -> bytes:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"
        return await self._get_bytes(path)
