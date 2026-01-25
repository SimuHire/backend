from __future__ import annotations


def assemble_result(
    *,
    status_str,
    passed_val,
    failed_val,
    total_val,
    run_id,
    run_status,
    conclusion,
    timeout,
    stdout,
    stderr,
    stdout_truncated,
    stderr_truncated,
    summary,
    last_run_at,
    workflow_run_id_str,
    commit_sha,
    workflow_url,
    commit_url,
    artifact_present,
    artifact_error,
    sanitized_output,
    include_output: bool,
):
    result = {
        "status": status_str,
        "passed": passed_val,
        "failed": failed_val,
        "total": total_val,
        "runId": run_id,
        "runStatus": run_status,
        "conclusion": conclusion,
        "timeout": timeout,
        "stdout": stdout,
        "stderr": stderr,
        "stdoutTruncated": stdout_truncated,
        "stderrTruncated": stderr_truncated,
        "summary": summary,
        "lastRunAt": last_run_at,
        "workflowRunId": workflow_run_id_str,
        "commitSha": commit_sha,
        "workflowUrl": workflow_url,
        "commitUrl": commit_url,
        "artifactName": "tenon-test-results" if artifact_present else None,
        "artifactPresent": True if artifact_present else None,
        "artifactErrorCode": artifact_error,
    }
    if include_output:
        result["output"] = sanitized_output
    return result
