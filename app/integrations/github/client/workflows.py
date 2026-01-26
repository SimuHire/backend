from __future__ import annotations

from .names import split_full_name
from .runs import WorkflowRun, parse_run
from .transport import GithubTransport


class WorkflowOperations:
    transport: GithubTransport

    async def trigger_workflow_dispatch(
        self,
        repo_full_name: str,
        workflow_id_or_file: str,
        *,
        ref: str,
        inputs: dict | None = None,
    ) -> None:
        owner, repo = split_full_name(repo_full_name)
        path = (
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id_or_file}/dispatches"
        )
        await self._request(
            "POST",
            path,
            json={"ref": ref, "inputs": inputs or {}},
            expect_body=False,
        )

    async def get_workflow_run(self, repo_full_name: str, run_id: int) -> WorkflowRun:
        owner, repo = split_full_name(repo_full_name)
        path = f"/repos/{owner}/{repo}/actions/runs/{run_id}"
        data = await self._get_json(path)
        return parse_run(data)

    async def list_workflow_runs(
        self,
        repo_full_name: str,
        workflow_id_or_file: str,
        *,
        branch: str | None = None,
        per_page: int = 5,
    ) -> list[WorkflowRun]:
        owner, repo = split_full_name(repo_full_name)
        params = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id_or_file}/runs"
        data = await self._get_json(path, params=params)
        runs = data.get("workflow_runs") or []
        return [parse_run(r) for r in runs]
