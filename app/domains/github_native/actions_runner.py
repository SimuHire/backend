from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
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
    poll_after_ms: int | None = None

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
        self._run_cache: OrderedDict[
            tuple[str, int], ActionsRunResult
        ] = OrderedDict()
        self._artifact_cache: OrderedDict[
            tuple[str, int, int], tuple[ParsedTestResults | None, str | None]
        ] = OrderedDict()
        self._poll_attempts: dict[tuple[str, int], int] = {}
        self._max_cache_entries = 128
        # Try preferred workflow file first, then Tenon defaults.
        self._workflow_fallbacks = list(
            dict.fromkeys(
                [
                    workflow_file,
                    "tenon-ci.yml",
                    ".github/workflows/tenon-ci.yml",
                ]
            )
        )

    async def dispatch_and_wait(
        self,
        *,
        repo_full_name: str,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> ActionsRunResult:
        """Trigger workflow_dispatch and poll until completion or timeout."""
        dispatch_started_at = datetime.now(UTC)
        workflow_file = await self._dispatch_with_fallbacks(
            repo_full_name, ref=ref, inputs=inputs
        )

        deadline = time.monotonic() + self.max_poll_seconds
        candidate: WorkflowRun | None = None
        while time.monotonic() < deadline:
            runs = await self.client.list_workflow_runs(
                repo_full_name, workflow_file, branch=ref, per_page=5
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
                    result = await self._build_result(repo_full_name, candidate)
                    self._cache_run_result((repo_full_name, candidate.id), result)
                    return result
            await asyncio.sleep(self.poll_interval_seconds)

        if candidate:
            result = self._normalize_run(candidate, running=True)
            self._apply_backoff((repo_full_name, candidate.id), result)
            self._cache_run_result((repo_full_name, candidate.id), result)
            return result
        raise GithubError("No workflow run found after dispatch")

    async def _dispatch_with_fallbacks(
        self, repo_full_name: str, *, ref: str, inputs: dict[str, Any] | None
    ) -> str:
        """Dispatch workflow, retrying alternative file names on 404."""
        errors: list[tuple[str, GithubError]] = []
        tried = []
        for wf in self._workflow_fallbacks:
            if wf in tried:
                continue
            tried.append(wf)
            try:
                await self.client.trigger_workflow_dispatch(
                    repo_full_name, wf, ref=ref, inputs=inputs
                )
                if wf != self.workflow_file:
                    logger.warning(
                        "github_workflow_dispatch_fallback",
                        extra={
                            "repo": repo_full_name,
                            "preferred_workflow": self.workflow_file,
                            "fallback_used": wf,
                        },
                    )
                return wf
            except GithubError as exc:
                errors.append((wf, exc))
                if exc.status_code and exc.status_code != 404:
                    raise
                continue
        # If we get here, all attempts failed; raise the last error.
        if errors:
            raise errors[-1][1]
        raise GithubError("Workflow dispatch failed")

    async def fetch_run_result(
        self, *, repo_full_name: str, run_id: int
    ) -> ActionsRunResult:
        """Fetch an existing workflow run and normalize."""
        cache_key = (repo_full_name, run_id)
        cached = self._run_cache.get(cache_key)
        if cached and cached.status != "running":
            return cached

        run = await self.client.get_workflow_run(repo_full_name, run_id)
        result = await self._build_result(repo_full_name, run)
        self._cache_run_result(cache_key, result)
        return result

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
        parsed, artifact_error = await self._parse_artifacts(repo_full_name, run.id)
        if parsed:
            base.passed = parsed.passed
            base.failed = parsed.failed
            base.total = parsed.total
            base.stdout = parsed.stdout
            base.stderr = parsed.stderr
            if base.raw is None:
                base.raw = {}
            base.raw["summary"] = parsed.summary
        elif artifact_error and run.conclusion:
            base.status = "error"
            if base.raw is None:
                base.raw = {}
            base.raw.setdefault("artifact_error", artifact_error)
            base.stderr = (
                base.stderr
                or "Test results artifact missing or unreadable. Please re-run tests."
            )
        cache_key = (repo_full_name, run.id)
        self._apply_backoff(cache_key, base)
        return base

    async def _parse_artifacts(
        self, repo_full_name: str, run_id: int
    ) -> tuple[ParsedTestResults | None, str | None]:
        artifacts = await self.client.list_artifacts(repo_full_name, run_id)
        preferred: list[dict[str, Any]] = []
        others: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not artifact or artifact.get("expired"):
                continue
            name = str(artifact.get("name") or "").lower()
            (preferred if name in PREFERRED_ARTIFACT_NAMES else others).append(artifact)

        found_artifact = False
        last_error: str | None = None
        for artifact in preferred + others:
            artifact_id = artifact.get("id")
            if not artifact_id:
                continue
            found_artifact = True
            cache_key = (repo_full_name, run_id, int(artifact_id))
            cached = self._artifact_cache.get(cache_key)
            if cached:
                parsed_cached, cached_error = cached
                if parsed_cached or cached_error:
                    return parsed_cached, cached_error
            try:
                content = await self.client.download_artifact_zip(
                    repo_full_name, int(artifact_id)
                )
            except GithubError:
                last_error = "artifact_download_failed"
                continue
            parsed = parse_test_results_zip(content)
            if parsed:
                self._cache_artifact_result(cache_key, parsed, None)
                return parsed, None
            last_error = "artifact_corrupt"
            self._cache_artifact_result(cache_key, None, last_error)
        if found_artifact:
            return None, last_error or "artifact_unavailable"
        return None, "artifact_missing"

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

    def _cache_run_result(
        self, key: tuple[str, int], result: ActionsRunResult
    ) -> None:
        self._run_cache[key] = result
        self._run_cache.move_to_end(key)
        if len(self._run_cache) > self._max_cache_entries:
            self._run_cache.popitem(last=False)
        if result.status != "running":
            self._poll_attempts.pop(key, None)

    def _cache_artifact_result(
        self,
        key: tuple[str, int, int],
        parsed: ParsedTestResults | None,
        error: str | None,
    ) -> None:
        self._artifact_cache[key] = (parsed, error)
        self._artifact_cache.move_to_end(key)
        if len(self._artifact_cache) > self._max_cache_entries:
            self._artifact_cache.popitem(last=False)

    def _apply_backoff(
        self, key: tuple[str, int], result: ActionsRunResult
    ) -> None:
        if result.status == "running":
            attempt = self._poll_attempts.get(key, 0) + 1
            self._poll_attempts[key] = attempt
            base_ms = int(self.poll_interval_seconds * 1000)
            result.poll_after_ms = min(base_ms * (2 ** (attempt - 1)), 15000)
        else:
            self._poll_attempts.pop(key, None)
            result.poll_after_ms = None
