from __future__ import annotations

from datetime import datetime, timedelta

from app.integrations.github.client import WorkflowRun


def _is_dispatched_run(run: WorkflowRun, dispatch_started_at: datetime) -> bool:
    if run.event != "workflow_dispatch":
        return False
    if run.created_at:
        try:
            created = datetime.fromisoformat(run.created_at.replace("Z", "+00:00"))
            return created >= dispatch_started_at - timedelta(seconds=10)
        except ValueError:
            return False
    return False
