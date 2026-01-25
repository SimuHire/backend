from __future__ import annotations

from app.domains.submissions.presenter.parsed_output_utils import (
    _OUTPUT_WHITELIST_KEYS,
    _safe_int,
    sanitize_stream,
)


def process_dict_output(
    parsed_output: dict, *, include_output: bool, max_output_chars: int
):
    passed_val = _safe_int(parsed_output.get("passed"))
    failed_val = _safe_int(parsed_output.get("failed"))
    total_val = _safe_int(parsed_output.get("total"))
    run_id = parsed_output.get("runId") or parsed_output.get("run_id")
    conclusion_raw = parsed_output.get("conclusion")
    conclusion = str(conclusion_raw).lower() if conclusion_raw else None
    timeout = parsed_output.get("timeout") is True or conclusion == "timed_out"
    summary_val = parsed_output.get("summary")
    summary = summary_val if isinstance(summary_val, dict) else None
    stdout, stdout_trunc = sanitize_stream(
        parsed_output.get("stdout"), max_chars=max_output_chars
    )
    stderr, stderr_trunc = sanitize_stream(
        parsed_output.get("stderr"), max_chars=max_output_chars
    )
    whitelisted = {
        key: parsed_output.get(key)
        for key in _OUTPUT_WHITELIST_KEYS
        if key in parsed_output
    }
    if parsed_output.get("stdout") is not None:
        whitelisted["stdout"] = stdout
    if parsed_output.get("stderr") is not None:
        whitelisted["stderr"] = stderr
    sanitized_output = whitelisted if include_output else None
    artifact_error = parsed_output.get("artifactErrorCode") or parsed_output.get(
        "artifact_error_code"
    )
    if isinstance(artifact_error, str):
        artifact_error = artifact_error.lower()
    return (
        passed_val,
        failed_val,
        total_val,
        run_id,
        conclusion,
        timeout,
        summary,
        stdout,
        stderr,
        stdout_trunc,
        stderr_trunc,
        sanitized_output,
        artifact_error,
    )
