from __future__ import annotations

from app.integrations.github.actions_runner.models import ActionsRunResult, RunStatus
from app.integrations.github.client import WorkflowRun


def normalize_run(
    run: WorkflowRun, *, timed_out: bool = False, running: bool = False
) -> ActionsRunResult:
    status = (run.status or "").lower()
    conclusion = (run.conclusion or "").lower() if run.conclusion else None
    if running or timed_out:
        normalized_status: RunStatus = "running"
    elif conclusion == "success":
        normalized_status = "passed"
    elif conclusion in {"failure", "timed_out", "cancelled"}:
        normalized_status = "failed"
    elif status in {"queued", "in_progress"}:
        normalized_status = "running"
    else:
        normalized_status = "error"
    return ActionsRunResult(
        status=normalized_status,
        run_id=int(run.id),
        conclusion=conclusion,
        passed=None,
        failed=None,
        total=None,
        stdout=None,
        stderr=None,
        head_sha=run.head_sha,
        html_url=run.html_url,
        raw={
            "status": run.status,
            "conclusion": run.conclusion,
            "artifact_count": run.artifact_count,
        },
    )
