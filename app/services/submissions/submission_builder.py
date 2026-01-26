from __future__ import annotations

from datetime import datetime

from app.domains import CandidateSession, Submission, Task
from app.integrations.github.workspaces.workspace import Workspace


def build_submission(
    *,
    candidate_session: CandidateSession,
    task: Task,
    payload,
    now: datetime,
    workspace: Workspace | None,
    diff_summary_json: str | None,
    commit_sha,
    workflow_run_id,
    tests_passed,
    tests_failed,
    test_output,
    last_run_at,
) -> Submission:
    return Submission(
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        submitted_at=now,
        content_text=payload.contentText,
        code_repo_path=workspace.repo_full_name if workspace else None,
        commit_sha=commit_sha,
        workflow_run_id=workflow_run_id,
        diff_summary_json=diff_summary_json,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        test_output=test_output,
        last_run_at=last_run_at,
    )
