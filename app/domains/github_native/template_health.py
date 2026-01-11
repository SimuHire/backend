from __future__ import annotations

import asyncio
import base64
import io
import json
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.core.brand import TEST_ARTIFACT_NAMESPACE
from app.domains.common.base import APIModel
from app.domains.github_native import GithubClient, GithubError, WorkflowRun
from app.domains.github_native.artifacts import PREFERRED_ARTIFACT_NAMES
from app.domains.tasks.template_catalog import TEMPLATE_CATALOG

WORKFLOW_DIR = ".github/workflows"
LEGACY_ARTIFACT_NAME = "simuhire-test-results"
RunMode = Literal["static", "live"]


class TemplateHealthChecks(APIModel):
    """Per-template health check details."""

    repoReachable: bool = False
    defaultBranch: str | None = None
    defaultBranchUsable: bool = False
    workflowFileExists: bool = False
    workflowHasUploadArtifact: bool = False
    workflowHasArtifactName: bool = False
    workflowHasTestResultsJson: bool = False


class TemplateHealthItem(APIModel):
    """Health status for a single template repo."""

    templateKey: str
    repoFullName: str
    workflowFile: str
    defaultBranch: str | None
    ok: bool
    errors: list[str]
    checks: TemplateHealthChecks
    mode: RunMode | None = None
    workflowRunId: int | None = None
    workflowConclusion: str | None = None
    artifactNameFound: str | None = None


class TemplateHealthResponse(APIModel):
    """Aggregate health status for all templates."""

    ok: bool
    templates: list[TemplateHealthItem]
    mode: RunMode | None = None


def _workflow_contract_checks(content: str) -> dict[str, bool]:
    text = content.lower()
    has_upload_artifact = "actions/upload-artifact" in text
    has_artifact_name = any(name.lower() in text for name in PREFERRED_ARTIFACT_NAMES)
    has_test_results_json = f"{TEST_ARTIFACT_NAMESPACE}.json" in text
    return {
        "workflowHasUploadArtifact": has_upload_artifact,
        "workflowHasArtifactName": has_artifact_name,
        "workflowHasTestResultsJson": has_test_results_json,
    }


def workflow_contract_errors(content: str) -> tuple[list[str], dict[str, bool]]:
    """Return contract errors and checks for a workflow file."""
    checks = _workflow_contract_checks(content)
    errors: list[str] = []
    if not checks["workflowHasUploadArtifact"]:
        errors.append("workflow_missing_upload_artifact")
    if not checks["workflowHasArtifactName"]:
        errors.append("workflow_missing_artifact_name")
    if not checks["workflowHasTestResultsJson"]:
        errors.append("workflow_missing_test_results_json")
    return errors, checks


def _validate_test_results_schema(payload: dict[str, Any]) -> bool:
    required = ["passed", "failed", "total", "stdout", "stderr"]
    if not all(key in payload for key in required):
        return False
    for key in ["passed", "failed", "total"]:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    for key in ["stdout", "stderr"]:
        value = payload.get(key)
        if not isinstance(value, str):
            return False
    summary = payload.get("summary")
    if summary is not None and not isinstance(summary, dict):
        return False
    return True


def _extract_test_results_json(content: bytes) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.endswith(f"{TEST_ARTIFACT_NAMESPACE}.json"):
                    with zf.open(name) as fp:
                        try:
                            data = json.load(fp)
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                            return None
                        if isinstance(data, dict):
                            return data
                        return None
    except zipfile.BadZipFile:
        return None
    return None


def _decode_contents(payload: dict[str, Any]) -> str | None:
    content = payload.get("content")
    encoding = payload.get("encoding")
    if not content:
        return None
    if encoding == "base64":
        try:
            normalized = "".join(str(content).split())
            decoded = base64.b64decode(normalized, validate=True).decode(
                "utf-8", errors="replace"
            )
        except (ValueError, UnicodeDecodeError):
            return None
        return decoded or None
    if isinstance(content, str):
        return content
    return None


def _is_dispatched_run(run: WorkflowRun, dispatch_started_at: datetime) -> bool:
    """Heuristic to select the workflow_dispatch run triggered after dispatch."""
    if run.event != "workflow_dispatch":
        return False
    if run.created_at:
        try:
            created = datetime.fromisoformat(run.created_at.replace("Z", "+00:00"))
            return created >= dispatch_started_at - timedelta(seconds=10)
        except ValueError:
            return False
    return False


def _classify_github_error(exc: GithubError) -> str | None:
    if exc.status_code == 403:
        return "github_forbidden"
    if exc.status_code == 429:
        return "github_rate_limited"
    return None


async def check_template_health(
    github_client: GithubClient,
    *,
    workflow_file: str,
    mode: RunMode = "static",
    template_keys: list[str] | None = None,
    timeout_seconds: int = 180,
    concurrency: int = 1,
) -> TemplateHealthResponse:
    """Validate all template repos against the Actions artifact contract."""
    selected = template_keys or list(TEMPLATE_CATALOG.keys())
    items: list[TemplateHealthItem] = []
    if concurrency <= 1:
        for template_key in selected:
            info = TEMPLATE_CATALOG[template_key]
            items.append(
                await _check_template_repo(
                    github_client,
                    template_key=template_key,
                    repo_full_name=info["repo_full_name"],
                    workflow_file=workflow_file,
                    mode=mode,
                    timeout_seconds=timeout_seconds,
                )
            )
    else:
        items = await _run_with_concurrency(
            selected,
            concurrency=concurrency,
            worker=lambda key: _check_template_repo(
                github_client,
                template_key=key,
                repo_full_name=TEMPLATE_CATALOG[key]["repo_full_name"],
                workflow_file=workflow_file,
                mode=mode,
                timeout_seconds=timeout_seconds,
            ),
        )
    return TemplateHealthResponse(
        ok=all(item.ok for item in items),
        templates=items,
        mode=mode,
    )


async def _check_template_repo(
    github_client: GithubClient,
    *,
    template_key: str,
    repo_full_name: str,
    workflow_file: str,
    mode: RunMode,
    timeout_seconds: int,
) -> TemplateHealthItem:
    errors: list[str] = []
    checks = TemplateHealthChecks()
    default_branch = None
    workflow_path = f"{WORKFLOW_DIR}/{workflow_file}"
    workflow_run_id = None
    workflow_conclusion = None
    artifact_name_found = None

    try:
        repo = await github_client.get_repo(repo_full_name)
        checks.repoReachable = True
    except GithubError as exc:
        classified = _classify_github_error(exc)
        if classified:
            errors.append(classified)
        elif exc.status_code == 404:
            errors.append("repo_not_found")
        else:
            errors.append("repo_unreachable")
        return TemplateHealthItem(
            templateKey=template_key,
            repoFullName=repo_full_name,
            workflowFile=workflow_file,
            defaultBranch=None,
            ok=False,
            errors=errors,
            checks=checks,
            mode=mode,
        )

    default_branch = (repo.get("default_branch") or "").strip() or None
    checks.defaultBranch = default_branch
    if not default_branch:
        errors.append("default_branch_missing")
    else:
        try:
            await github_client.get_branch(repo_full_name, default_branch)
            checks.defaultBranchUsable = True
        except GithubError as exc:
            classified = _classify_github_error(exc)
            errors.append(classified or "default_branch_unusable")

    if default_branch:
        try:
            contents = await github_client.get_file_contents(
                repo_full_name, workflow_path, ref=default_branch
            )
            decoded = _decode_contents(contents)
            if not decoded:
                errors.append("workflow_file_unreadable")
            else:
                checks.workflowFileExists = True
                contract_errors, contract_checks = workflow_contract_errors(decoded)
                checks.workflowHasUploadArtifact = contract_checks[
                    "workflowHasUploadArtifact"
                ]
                checks.workflowHasArtifactName = contract_checks[
                    "workflowHasArtifactName"
                ]
                checks.workflowHasTestResultsJson = contract_checks[
                    "workflowHasTestResultsJson"
                ]
                errors.extend(contract_errors)
        except GithubError as exc:
            classified = _classify_github_error(exc)
            if classified:
                errors.append(classified)
            elif exc.status_code == 404:
                errors.append("workflow_file_missing")
            else:
                errors.append("workflow_file_unreadable")

    if mode == "live" and not errors and default_branch:
        live = await _run_live_check(
            github_client,
            repo_full_name=repo_full_name,
            workflow_file=workflow_file,
            default_branch=default_branch,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(live.errors)
        workflow_run_id = live.workflow_run_id
        workflow_conclusion = live.workflow_conclusion
        artifact_name_found = live.artifact_name_found

    return TemplateHealthItem(
        templateKey=template_key,
        repoFullName=repo_full_name,
        workflowFile=workflow_file,
        defaultBranch=default_branch,
        ok=len(errors) == 0,
        errors=errors,
        checks=checks,
        mode=mode,
        workflowRunId=workflow_run_id,
        workflowConclusion=workflow_conclusion,
        artifactNameFound=artifact_name_found,
    )


@dataclass
class _LiveCheckResult:
    errors: list[str]
    workflow_run_id: int | None
    workflow_conclusion: str | None
    artifact_name_found: str | None


async def _run_live_check(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    timeout_seconds: int,
) -> _LiveCheckResult:
    errors: list[str] = []
    workflow_run_id = None
    workflow_conclusion = None
    artifact_name_found = None
    dispatch_started_at = datetime.now(UTC)

    try:
        await github_client.trigger_workflow_dispatch(
            repo_full_name, workflow_file, ref=default_branch
        )
    except GithubError as exc:
        classified = _classify_github_error(exc)
        errors.append(classified or "workflow_dispatch_failed")
        return _LiveCheckResult(errors, None, None, None)

    deadline = time.monotonic() + timeout_seconds
    poll_interval = 2.0
    run: WorkflowRun | None = None

    while time.monotonic() < deadline:
        try:
            runs = await github_client.list_workflow_runs(
                repo_full_name, workflow_file, branch=default_branch, per_page=5
            )
        except GithubError as exc:
            classified = _classify_github_error(exc)
            if classified:
                errors.append(classified)
                return _LiveCheckResult(errors, None, None, None)
            errors.append("workflow_dispatch_failed")
            return _LiveCheckResult(errors, None, None, None)

        candidate = None
        for item in runs:
            if _is_dispatched_run(item, dispatch_started_at):
                candidate = item
                break
        if candidate:
            run = candidate
            status = (candidate.status or "").lower()
            conclusion = (
                (candidate.conclusion or "").lower() if candidate.conclusion else None
            )
            if status == "completed" or conclusion:
                workflow_run_id = int(candidate.id)
                workflow_conclusion = conclusion
                break

        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 8.0)

    if run is None or workflow_run_id is None:
        return _LiveCheckResult(["workflow_run_timeout"], None, None, None)

    if workflow_conclusion and workflow_conclusion != "success":
        errors.append("workflow_run_not_success")

    try:
        artifacts = await github_client.list_artifacts(repo_full_name, workflow_run_id)
    except GithubError as exc:
        classified = _classify_github_error(exc)
        return _LiveCheckResult(
            [classified or "artifact_missing"],
            workflow_run_id,
            workflow_conclusion,
            None,
        )

    tenon_artifact = None
    legacy_artifact = None
    for artifact in artifacts:
        if not artifact or artifact.get("expired"):
            continue
        name = str(artifact.get("name") or "")
        lowered = name.lower()
        if lowered == LEGACY_ARTIFACT_NAME:
            legacy_artifact = artifact
            artifact_name_found = name
        if lowered == TEST_ARTIFACT_NAMESPACE:
            tenon_artifact = artifact
            artifact_name_found = name

    if tenon_artifact is None:
        if legacy_artifact:
            errors.append("artifact_legacy_name_simuhire")
        else:
            errors.append("artifact_missing")
        return _LiveCheckResult(
            errors, workflow_run_id, workflow_conclusion, artifact_name_found
        )

    artifact_id = tenon_artifact.get("id")
    if not artifact_id:
        errors.append("artifact_missing")
        return _LiveCheckResult(
            errors, workflow_run_id, workflow_conclusion, artifact_name_found
        )

    try:
        zip_content = await github_client.download_artifact_zip(
            repo_full_name, int(artifact_id)
        )
    except GithubError as exc:
        classified = _classify_github_error(exc)
        errors.append(classified or "artifact_missing")
        return _LiveCheckResult(
            errors, workflow_run_id, workflow_conclusion, artifact_name_found
        )

    payload = _extract_test_results_json(zip_content)
    if payload is None:
        errors.append("artifact_zip_missing_test_results_json")
        return _LiveCheckResult(
            errors, workflow_run_id, workflow_conclusion, artifact_name_found
        )

    if not _validate_test_results_schema(payload):
        errors.append("test_results_json_invalid_schema")

    return _LiveCheckResult(
        errors, workflow_run_id, workflow_conclusion, artifact_name_found
    )


async def _run_with_concurrency(
    template_keys: list[str],
    *,
    concurrency: int,
    worker,
) -> list[TemplateHealthItem]:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[TemplateHealthItem] = [None] * len(template_keys)  # type: ignore[list-item]

    async def _run_one(index: int, key: str) -> None:
        async with semaphore:
            results[index] = await worker(key)

    await asyncio.gather(
        *[_run_one(index, key) for index, key in enumerate(template_keys)]
    )
    return results
