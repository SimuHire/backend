from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.domains.github_native.artifacts import (
    PREFERRED_ARTIFACT_NAMES,
    ParsedTestResults,
    parse_test_results_zip,
)
from app.domains.github_native.client import GithubClient, GithubError, WorkflowRun

logger = logging.getLogger(__name__)

RunStatus = Literal["passed", "failed", "running", "error"]


@dataclass
class ActionsRunResult:
    """Normalized GitHub Actions run result."""

    status: RunStatus
    run_id: int
    conclusion: str | None
    passed: int | None
    failed: int | None
    total: int | None
    stdout: str | None
    stderr: str | None
    head_sha: str | None
    html_url: str | None
    raw: dict[str, Any] | None = None

    @property
    def as_test_output(self) -> dict[str, Any]:
        """Convert to a serializable test output structure."""
        payload = {
            "status": self.status,
            "runId": self.run_id,
            "conclusion": self.conclusion,
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if self.raw and "summary" in self.raw:
            payload["summary"] = self.raw.get("summary")
        return payload


class GithubActionsRunner:
    """Helper to dispatch workflow runs and normalize results."""

    def __init__(
        self,
        client: GithubClient,
        *,
        workflow_file: str,
        poll_interval_seconds: float = 2.0,
        max_poll_seconds: float = 120.0,
    ):
        self.client = client
        self.workflow_file = workflow_file
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_seconds = max_poll_seconds

    async def dispatch_and_wait(
        self,
        *,
        repo_full_name: str,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> ActionsRunResult:
        """Trigger workflow_dispatch and poll until completion or timeout."""
        dispatch_started_at = datetime.now(UTC)
        await self.client.trigger_workflow_dispatch(
            repo_full_name, self.workflow_file, ref=ref, inputs=inputs
        )

        deadline = time.monotonic() + self.max_poll_seconds
        candidate: WorkflowRun | None = None
        while time.monotonic() < deadline:
            runs = await self.client.list_workflow_runs(
                repo_full_name, self.workflow_file, branch=ref, per_page=5
            )
            for run in runs:
                if self._is_dispatched_run(run, dispatch_started_at):
                    candidate = run
                    break
            if candidate:
                status = (candidate.status or "").lower()
                conclusion = (
                    (candidate.conclusion or "").lower()
                    if candidate.conclusion
                    else None
                )
                if conclusion or status == "completed":
                    return await self._build_result(repo_full_name, candidate)
            await asyncio.sleep(self.poll_interval_seconds)

        if candidate:
            return self._normalize_run(candidate, running=True)
        raise GithubError("No workflow run found after dispatch")

    async def fetch_run_result(
        self, *, repo_full_name: str, run_id: int
    ) -> ActionsRunResult:
        """Fetch an existing workflow run and normalize."""
        run = await self.client.get_workflow_run(repo_full_name, run_id)
        return await self._build_result(repo_full_name, run)

    def _normalize_run(
        self, run: WorkflowRun, *, timed_out: bool = False, running: bool = False
    ) -> ActionsRunResult:
        status = (run.status or "").lower()
        conclusion = (run.conclusion or "").lower() if run.conclusion else None

        if running:
            normalized_status: RunStatus = "running"
        elif timed_out:
            normalized_status = "running"
        elif conclusion == "success":
            normalized_status = "passed"
        elif conclusion in {"failure", "timed_out", "cancelled"}:
            normalized_status = "failed"
        elif status in {"queued", "in_progress"}:
            normalized_status = "running"
        else:
            normalized_status = "error"

        passed = None
        failed = None
        total = None
        # Placeholder for future artifact parsing. Keep counts nullable for now.

        stdout = None
        stderr = None

        return ActionsRunResult(
            status=normalized_status,
            run_id=int(run.id),
            conclusion=conclusion,
            passed=passed,
            failed=failed,
            total=total,
            stdout=stdout,
            stderr=stderr,
            head_sha=run.head_sha,
            html_url=run.html_url,
            raw={
                "status": run.status,
                "conclusion": run.conclusion,
                "artifact_count": run.artifact_count,
            },
        )

    async def _build_result(
        self, repo_full_name: str, run: WorkflowRun
    ) -> ActionsRunResult:
        base = self._normalize_run(run)
        parsed = await self._parse_artifacts(repo_full_name, run.id)
        if parsed:
            base.passed = parsed.passed
            base.failed = parsed.failed
            base.total = parsed.total
            base.stdout = parsed.stdout
            base.stderr = parsed.stderr
            if base.raw is None:
                base.raw = {}
            base.raw["summary"] = parsed.summary
        return base

    async def _parse_artifacts(
        self, repo_full_name: str, run_id: int
    ) -> ParsedTestResults | None:
        artifacts = await self.client.list_artifacts(repo_full_name, run_id)
        preferred: list[dict[str, Any]] = []
        others: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not artifact or artifact.get("expired"):
                continue
            name = str(artifact.get("name") or "").lower()
            (preferred if name in PREFERRED_ARTIFACT_NAMES else others).append(artifact)

        for artifact in preferred + others:
            artifact_id = artifact.get("id")
            if not artifact_id:
                continue
            try:
                content = await self.client.download_artifact_zip(
                    repo_full_name, int(artifact_id)
                )
            except GithubError:
                continue
            parsed = parse_test_results_zip(content)
            if parsed:
                return parsed
        return None

    def _is_dispatched_run(
        self, run: WorkflowRun, dispatch_started_at: datetime
    ) -> bool:
        """Heuristic to select the workflow_dispatch run triggered after dispatch_started."""
        if run.event and run.event != "workflow_dispatch":
            return False
        if run.created_at:
            try:
                created = datetime.fromisoformat(run.created_at.replace("Z", "+00:00"))
                return created >= dispatch_started_at - timedelta(seconds=10)
            except ValueError:
                return False
        return False
