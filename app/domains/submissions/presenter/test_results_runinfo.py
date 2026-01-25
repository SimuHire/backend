from __future__ import annotations


def enrich_run_info(sub, run_id, conclusion, timeout):
    workflow_run_id = getattr(sub, "workflow_run_id", None)
    commit_sha = getattr(sub, "commit_sha", None)
    last_run_at = getattr(sub, "last_run_at", None)
    if run_id is None and workflow_run_id:
        try:
            run_id = int(workflow_run_id)
        except (TypeError, ValueError):
            run_id = workflow_run_id

    db_status = getattr(sub, "workflow_run_status", None)
    run_status = db_status.lower() if isinstance(db_status, str) else None
    db_conclusion = getattr(sub, "workflow_run_conclusion", None)
    if isinstance(db_conclusion, str):
        conclusion = db_conclusion.lower()
    if timeout is None and conclusion == "timed_out":
        timeout = True
    workflow_run_id_str = str(workflow_run_id) if workflow_run_id is not None else None
    return (
        run_id,
        conclusion,
        timeout,
        run_status,
        workflow_run_id_str,
        commit_sha,
        last_run_at,
    )
