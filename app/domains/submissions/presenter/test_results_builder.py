from __future__ import annotations

from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.presenter.test_results_assemble import assemble_result
from app.domains.submissions.presenter.test_results_counts import fill_counts
from app.domains.submissions.presenter.test_results_guard import should_skip
from app.domains.submissions.presenter.test_results_kwargs import build_result_kwargs
from app.domains.submissions.presenter.test_results_payload import extract_payload
from app.domains.submissions.presenter.test_results_runinfo import enrich_run_info


def build_test_results(
    sub,
    parsed_output,
    *,
    workflow_url: str | None,
    commit_url: str | None,
    include_output: bool,
    max_output_chars: int,
):
    parsed_payload = parsed_output or None
    payload = extract_payload(
        parsed_payload, include_output=include_output, max_output_chars=max_output_chars
    )
    passed_val, failed_val, total_val = fill_counts(
        sub, payload["passed_val"], payload["failed_val"], payload["total_val"]
    )
    status_str = recruiter_sub_service.derive_test_status(
        passed_val, failed_val, parsed_payload
    )
    (
        run_id,
        conclusion,
        timeout,
        run_status,
        workflow_run_id_str,
        commit_sha,
        last_run_at,
    ) = enrich_run_info(
        sub, payload["run_id"], payload["conclusion"], payload["timeout"]
    )
    if should_skip(
        status_str,
        passed_val,
        failed_val,
        total_val,
        payload["sanitized_output"],
        workflow_run_id_str,
        commit_sha,
        last_run_at,
    ):
        return None
    kwargs = build_result_kwargs(
        status_str=status_str,
        passed_val=passed_val,
        failed_val=failed_val,
        total_val=total_val,
        run_id=run_id,
        run_status=run_status,
        conclusion=conclusion,
        timeout=timeout,
        payload=payload,
        last_run_at=last_run_at,
        workflow_run_id_str=workflow_run_id_str,
        commit_sha=commit_sha,
        workflow_url=workflow_url,
        commit_url=commit_url,
        include_output=include_output,
    )
    return assemble_result(**kwargs)
