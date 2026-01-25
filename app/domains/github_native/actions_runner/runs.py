from __future__ import annotations

from datetime import datetime, timedelta

from app.domains.github_native.client import WorkflowRun


def is_dispatched_run(run: WorkflowRun, dispatch_started_at: datetime) -> bool:
    if run.event and run.event != "workflow_dispatch":
        return False
    if run.created_at:
        try:
            created = datetime.fromisoformat(run.created_at.replace("Z", "+00:00"))
            return created >= dispatch_started_at - timedelta(seconds=10)
        except ValueError:
            return False
    return False


def run_cache_key(repo_full_name: str, run_id: int) -> tuple[str, int]:
    return (repo_full_name, int(run_id))
