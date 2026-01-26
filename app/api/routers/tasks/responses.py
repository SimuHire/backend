from app.domains.submissions.schemas import RunTestsResponse
from app.integrations.github.actions_runner import ActionsRunResult


def build_run_response(result: ActionsRunResult) -> RunTestsResponse:
    """Render a workflow run result into API response shape."""
    return RunTestsResponse(
        status=result.status,
        passed=result.passed,
        failed=result.failed,
        total=result.total,
        stdout=result.stdout,
        stderr=result.stderr,
        timeout=result.conclusion == "timed_out",
        runId=result.run_id,
        conclusion=result.conclusion,
        workflowUrl=result.html_url,
        commitSha=result.head_sha,
        pollAfterMs=result.poll_after_ms,
    )
