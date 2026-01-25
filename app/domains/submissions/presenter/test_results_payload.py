from __future__ import annotations

from app.domains.submissions.presenter.parsed_output import process_parsed_output


def extract_payload(
    parsed_payload, *, include_output: bool, max_output_chars: int
) -> dict:
    (
        passed_val,
        failed_val,
        total_val,
        run_id,
        conclusion,
        timeout,
        summary,
        stdout,
        stderr,
        stdout_truncated,
        stderr_truncated,
        sanitized_output,
        artifact_error,
    ) = process_parsed_output(
        parsed_payload, include_output=include_output, max_output_chars=max_output_chars
    )
    return {
        "parsed_payload_present": parsed_payload is not None,
        "passed_val": passed_val,
        "failed_val": failed_val,
        "total_val": total_val,
        "run_id": run_id,
        "conclusion": conclusion,
        "timeout": timeout,
        "summary": summary,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "sanitized_output": sanitized_output,
        "artifact_error": artifact_error,
    }
