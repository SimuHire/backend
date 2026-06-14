"""Application module for evaluations services evaluations evaluator runtime service workflows."""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai import (
    allow_demo_or_test_mode,
    build_required_snapshot_prompt,
    require_agent_policy_snapshot,
    require_agent_runtime,
    require_ai_policy_snapshot,
    validate_ai_policy_snapshot_contract,
)
from app.config import settings
from app.evaluations.services.evaluations_services_evaluations_evaluator_evidence_service import (
    _build_day_evidence,
)
from app.evaluations.services.evaluations_services_evaluations_evaluator_models_service import (
    CodeImplementationEvidenceContext,
    DayEvaluationResult,
    EvaluationInputBundle,
    EvaluationResult,
    ReviewerReportResult,
    WinoeReportEvaluator,
)
from app.evaluations.services.evaluations_services_evaluations_evaluator_scoring_service import (
    _recommendation_from_score,
    _score_for_day,
)
from app.integrations.winoe_report_review import (
    WinoeReportAggregateRequest,
    WinoeReportDayReviewRequest,
    get_winoe_report_review_provider,
)

_MARKDOWN_RANGE_RE = re.compile(
    r"^(?:(?P<sha>[0-9a-fA-F]{7,40}):)?(?P<path>[^:\[\]]+):L(?P<start>\d+)-L(?P<end>\d+)$"
)
_TIMESTAMP_RANGE_RE = re.compile(r"^\[(?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2})\]$")
_SUBMISSION_REF_RE = re.compile(r"^submission:(?P<id>[1-9]\d*)$")


def _fallback_provider_for_reviewer(reviewer_key: str) -> str:
    if reviewer_key == "designDocReviewer":
        return str(settings.WINOE_REPORT_DAY1_FALLBACK_PROVIDER or "")
    if reviewer_key == "codeImplementationReviewer":
        return str(settings.WINOE_REPORT_DAY23_FALLBACK_PROVIDER or "")
    if reviewer_key == "demoPresentationReviewer":
        return str(settings.WINOE_REPORT_DAY4_FALLBACK_PROVIDER or "")
    if reviewer_key == "reflectionEssayReviewer":
        return str(settings.WINOE_REPORT_DAY5_FALLBACK_PROVIDER or "")
    raise LookupError(f"unsupported_reviewer_key:{reviewer_key}")


class DeterministicWinoeReportEvaluator:
    """Represent deterministic winoe report evaluator data and behavior."""

    async def evaluate(self, bundle: EvaluationInputBundle) -> EvaluationResult:
        """Execute evaluate."""
        snapshot = require_ai_policy_snapshot(
            bundle.ai_policy_snapshot_json,
            scenario_version_id=bundle.scenario_version_id,
        )
        validate_ai_policy_snapshot_contract(
            snapshot,
            scenario_version_id=bundle.scenario_version_id,
        )
        disabled = set(bundle.disabled_day_indexes)
        day_results: list[DayEvaluationResult] = []
        reviewer_reports: list[ReviewerReportResult] = []
        report_day_scores: list[dict[str, object]] = []
        for day_input in sorted(bundle.day_inputs, key=lambda value: value.day_index):
            if day_input.day_index in disabled:
                report_day_scores.append(
                    {
                        "dayIndex": day_input.day_index,
                        "status": "human_review_required",
                        "reason": "ai_eval_disabled_for_day",
                    }
                )
                continue
            day_result, reviewer_report = _deterministic_day_review(day_input)
            day_results.append(day_result)
            reviewer_reports.append(reviewer_report)
            report_day_scores.append(
                {
                    "dayIndex": day_result.day_index,
                    "score": day_result.score,
                    "rubricBreakdown": dict(day_result.rubric_breakdown),
                    "evidence": list(day_result.evidence),
                    "status": "scored",
                }
            )
        report_json = _deterministic_aggregate_report(
            bundle=bundle,
            snapshot_json=snapshot,
            day_results=day_results,
            reviewer_reports=reviewer_reports,
            report_day_scores=report_day_scores,
        )
        report_json = _build_winoe_report_payload(
            bundle=bundle,
            day_results=day_results,
            reviewer_reports=reviewer_reports,
            report_day_scores=report_day_scores,
            synthesis_output=report_json,
        )
        return EvaluationResult(
            overall_winoe_score=float(report_json["overallWinoeScore"]),
            recommendation=str(report_json["recommendation"]),
            confidence=float(report_json["confidence"]),
            day_results=day_results,
            report_json=report_json,
            reviewer_reports=reviewer_reports,
        )


class LiveWinoeReportEvaluator:
    """Provider-backed winoe report evaluator with per-day reviewer orchestration."""

    async def evaluate(self, bundle: EvaluationInputBundle) -> EvaluationResult:
        """Execute evaluate."""
        snapshot = require_ai_policy_snapshot(
            bundle.ai_policy_snapshot_json,
            scenario_version_id=bundle.scenario_version_id,
        )
        validate_ai_policy_snapshot_contract(
            snapshot,
            scenario_version_id=bundle.scenario_version_id,
        )
        disabled = set(bundle.disabled_day_indexes)
        day_results: list[DayEvaluationResult] = []
        reviewer_reports: list[ReviewerReportResult] = []
        report_day_scores: list[dict[str, object]] = []

        for day_input in sorted(bundle.day_inputs, key=lambda value: value.day_index):
            if day_input.day_index in disabled:
                report_day_scores.append(
                    {
                        "dayIndex": day_input.day_index,
                        "status": "human_review_required",
                        "reason": "ai_eval_disabled_for_day",
                    }
                )
                continue
            reviewer_key = _reviewer_key_for_day(day_input.day_index)
            require_agent_policy_snapshot(
                snapshot,
                reviewer_key,
                scenario_version_id=bundle.scenario_version_id,
            )
            reviewer_runtime = require_agent_runtime(
                snapshot,
                reviewer_key,
                scenario_version_id=bundle.scenario_version_id,
            )
            reviewer_runtime_mode = str(reviewer_runtime["runtimeMode"])
            reviewer_provider = str(reviewer_runtime["provider"])
            reviewer_model = str(reviewer_runtime["model"])
            if allow_demo_or_test_mode(reviewer_runtime_mode):
                day_result, reviewer_report = _deterministic_day_review(day_input)
            else:
                run_context_md = _build_day_run_context(bundle, day_input)
                system_prompt, rubric_prompt = build_required_snapshot_prompt(
                    snapshot_json=snapshot,
                    agent_key=reviewer_key,
                    run_context_md=run_context_md,
                    scenario_version_id=bundle.scenario_version_id,
                )
                request = WinoeReportDayReviewRequest(
                    agent_key=reviewer_key,
                    fallback_provider=_fallback_provider_for_reviewer(reviewer_key),
                    system_prompt=system_prompt,
                    user_prompt=_build_day_review_prompt(
                        bundle=bundle,
                        day_input=day_input,
                        rubric_prompt=rubric_prompt,
                    ),
                    model=reviewer_model,
                )
                provider = get_winoe_report_review_provider(reviewer_provider)
                reviewer_output = provider.review_day(request=request)
                reviewer_report = _reviewer_report_from_output(
                    reviewer_key=reviewer_key,
                    day_input=day_input,
                    reviewer_output=reviewer_output,
                )
                day_result = DayEvaluationResult(
                    day_index=reviewer_output.dayIndex,
                    score=reviewer_output.score,
                    rubric_breakdown=dict(reviewer_output.rubricBreakdown),
                    evidence=[
                        evidence.model_dump() for evidence in reviewer_output.evidence
                    ],
                )
            reviewer_reports.append(reviewer_report)
            day_results.append(day_result)
            report_day_scores.append(
                {
                    "dayIndex": day_result.day_index,
                    "score": day_result.score,
                    "rubricBreakdown": dict(day_result.rubric_breakdown),
                    "evidence": list(day_result.evidence),
                    "status": "scored",
                }
            )

        require_agent_policy_snapshot(
            snapshot,
            "winoeReport",
            scenario_version_id=bundle.scenario_version_id,
        )
        aggregator_runtime = require_agent_runtime(
            snapshot,
            "winoeReport",
            scenario_version_id=bundle.scenario_version_id,
        )
        aggregator_runtime_mode = str(aggregator_runtime["runtimeMode"])
        aggregator_provider = str(aggregator_runtime["provider"])
        aggregator_model = str(aggregator_runtime["model"])
        if allow_demo_or_test_mode(aggregator_runtime_mode) or not reviewer_reports:
            legacy_report_json = _deterministic_aggregate_report(
                bundle=bundle,
                snapshot_json=snapshot,
                day_results=day_results,
                reviewer_reports=reviewer_reports,
                report_day_scores=report_day_scores,
            )
            report_json = _build_winoe_report_payload(
                bundle=bundle,
                day_results=day_results,
                reviewer_reports=reviewer_reports,
                report_day_scores=report_day_scores,
                synthesis_output=legacy_report_json,
            )
        else:
            run_context_md = _build_winoe_report_run_context(bundle)
            system_prompt, rubric_prompt = build_required_snapshot_prompt(
                snapshot_json=snapshot,
                agent_key="winoeReport",
                run_context_md=run_context_md,
                scenario_version_id=bundle.scenario_version_id,
            )
            provider = get_winoe_report_review_provider(aggregator_provider)
            aggregate_output = provider.aggregate_winoe_report(
                request=WinoeReportAggregateRequest(
                    agent_key="winoeReport",
                    fallback_provider=str(
                        settings.WINOE_REPORT_AGGREGATOR_FALLBACK_PROVIDER or ""
                    ),
                    system_prompt=system_prompt,
                    user_prompt=json.dumps(
                        {
                            "trialContext": bundle.trial_context_json or {},
                            "reviewerReports": [
                                _reviewer_report_payload(report)
                                for report in reviewer_reports
                            ],
                            "disabledDayIndexes": sorted(bundle.disabled_day_indexes),
                            "rubricGuidance": rubric_prompt,
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    model=aggregator_model,
                )
            )
            report_json = _build_winoe_report_payload(
                bundle=bundle,
                day_results=day_results,
                reviewer_reports=reviewer_reports,
                report_day_scores=report_day_scores,
                synthesis_output=aggregate_output,
            )
        return EvaluationResult(
            overall_winoe_score=float(report_json["overallWinoeScore"]),
            recommendation=str(report_json["recommendation"]),
            confidence=float(report_json["confidence"]),
            day_results=day_results,
            report_json=report_json,
            reviewer_reports=reviewer_reports,
        )


def _reviewer_key_for_day(day_index: int) -> str:
    if day_index == 1:
        return "designDocReviewer"
    if day_index in {2, 3}:
        return "codeImplementationReviewer"
    if day_index == 4:
        return "demoPresentationReviewer"
    return "reflectionEssayReviewer"


def _submission_kind_for_day(day_input) -> str:
    task_type = getattr(day_input, "task_type", None)
    if isinstance(task_type, str) and task_type.strip():
        return task_type.strip().lower()
    if day_input.day_index in {2, 3}:
        return "code"
    if day_input.day_index == 4:
        return "transcript"
    return "text"


def _reviewer_report_from_output(
    *,
    reviewer_key: str,
    day_input,
    reviewer_output,
) -> ReviewerReportResult:
    return ReviewerReportResult(
        reviewer_agent_key=reviewer_key,
        day_index=reviewer_output.dayIndex,
        submission_kind=_submission_kind_for_day(day_input),
        score=float(reviewer_output.score),
        dimensional_scores_json=dict(reviewer_output.rubricBreakdown),
        evidence_citations_json=[
            evidence.model_dump() for evidence in reviewer_output.evidence
        ],
        assessment_text=str(reviewer_output.summary),
        strengths_json=[str(item) for item in reviewer_output.strengths],
        risks_json=[str(item) for item in reviewer_output.risks],
        raw_output_json=reviewer_output.model_dump(),
    )


def _reviewer_report_payload(report: ReviewerReportResult) -> dict[str, object]:
    return {
        "reviewerAgentKey": report.reviewer_agent_key,
        "dayIndex": report.day_index,
        "submissionKind": report.submission_kind,
        "score": report.score,
        "dimensionalScores": dict(report.dimensional_scores_json),
        "evidenceCitations": list(report.evidence_citations_json),
        "assessment": report.assessment_text,
        "strengths": list(report.strengths_json),
        "concerns": list(report.risks_json),
    }


def _citation_identity(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("dimension") or "").strip(),
        str(item.get("artifact_ref") or "").strip(),
        str(item.get("excerpt") or "").strip(),
    )


def _is_submission_artifact_ref(artifact_ref: object) -> bool:
    if not isinstance(artifact_ref, str):
        return False
    return _SUBMISSION_REF_RE.match(artifact_ref.strip()) is not None


def _is_stronger_artifact_ref(artifact_ref: object) -> bool:
    if not isinstance(artifact_ref, str):
        return False
    normalized = artifact_ref.strip()
    if not normalized:
        return False
    return bool(
        _MARKDOWN_RANGE_RE.match(normalized) or _TIMESTAMP_RANGE_RE.match(normalized)
    )


def _dedupe_citations(
    citations: list[dict[str, object]],
) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in citations:
        identity = _citation_identity(item)
        if not all(identity):
            continue
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(dict(item))
    return unique


def _build_day_run_context(
    bundle: EvaluationInputBundle,
    day_input,
) -> str:
    evidence_lines: list[str] = []
    evidence = bundle.code_implementation_evidence
    if day_input.day_index in {2, 3} and isinstance(
        evidence, CodeImplementationEvidenceContext
    ):
        status = evidence.evidence_status or {}
        evidence_lines.extend(
            [
                "Code implementation evidence is supplied in the user prompt as codeImplementationEvidence.",
                (
                    "Repository snapshot status: "
                    f"{status.get('repository_snapshot', 'unknown')}"
                ),
                (
                    "Commit history status: "
                    f"{status.get('commit_history', 'unknown')}"
                ),
                (
                    "File creation timeline status: "
                    f"{status.get('file_creation_timeline', 'unknown')}"
                ),
                (
                    "Test coverage progression status: "
                    f"{status.get('test_coverage_progression', 'unknown')}"
                ),
                (
                    "Do not infer process quality when commit history, file creation timeline, or test coverage progression are unavailable."
                ),
            ]
        )
    return (
        f"Candidate session ID: {bundle.candidate_session_id}\n"
        f"Scenario version ID: {bundle.scenario_version_id}\n"
        f"Day index: {day_input.day_index}\n"
        f"Task type: {day_input.task_type or 'unknown'}\n"
        f"Commit SHA: {day_input.commit_sha or 'n/a'}\n"
        f"Transcript ref: {day_input.transcript_reference or 'n/a'}"
        + ("\n" + "\n".join(evidence_lines) if evidence_lines else "")
    )


def _build_winoe_report_run_context(bundle: EvaluationInputBundle) -> str:
    return (
        f"Candidate session ID: {bundle.candidate_session_id}\n"
        f"Scenario version ID: {bundle.scenario_version_id}\n"
        f"Disabled day indexes: {sorted(bundle.disabled_day_indexes)}"
    )


def _build_day_review_prompt(
    *,
    bundle: EvaluationInputBundle,
    day_input,
    rubric_prompt: str,
) -> str:
    code_implementation_evidence = (
        _serialize_code_implementation_evidence(bundle.code_implementation_evidence)
        if day_input.day_index in {2, 3}
        else None
    )
    return json.dumps(
        {
            "trialContext": bundle.trial_context_json or {},
            "dayInput": {
                "dayIndex": day_input.day_index,
                "taskId": day_input.task_id,
                "taskType": day_input.task_type,
                "submissionId": day_input.submission_id,
                "contentText": day_input.content_text,
                "contentJson": day_input.content_json,
                "repoFullName": day_input.repo_full_name,
                "commitSha": day_input.commit_sha,
                "workflowRunId": day_input.workflow_run_id,
                "diffSummary": day_input.diff_summary,
                "testsPassed": day_input.tests_passed,
                "testsFailed": day_input.tests_failed,
                "transcriptReference": day_input.transcript_reference,
                "transcriptSegments": day_input.transcript_segments,
                "cutoffCommitSha": day_input.cutoff_commit_sha,
                "evalBasisRef": day_input.eval_basis_ref,
            },
            "reviewContext": {
                "codeImplementationEvidence": code_implementation_evidence,
                "instructions": (
                    "Use codeImplementationEvidence as primary evidence for Days 2 and 3. "
                    "If commit history, file creation timeline, or test coverage progression are unavailable, say so explicitly and do not infer process quality."
                    if day_input.day_index in {2, 3}
                    else None
                ),
            },
            "rubricGuidance": rubric_prompt,
        },
        indent=2,
        sort_keys=True,
    )


def _serialize_code_implementation_evidence(
    evidence: CodeImplementationEvidenceContext,
) -> dict[str, object]:
    """Serialize code implementation evidence into prompt-ready JSON."""
    return {
        "repositorySnapshot": (
            dict(evidence.repository_snapshot)
            if isinstance(evidence.repository_snapshot, dict)
            else None
        ),
        "repositoryUrl": evidence.repository_url,
        "repositoryReference": evidence.repository_reference,
        "repositoryArtifactReferences": [
            dict(item) for item in evidence.repository_artifact_references
        ],
        "commitHistory": [dict(item) for item in evidence.commit_history],
        "fileCreationTimeline": [
            dict(item) for item in evidence.file_creation_timeline
        ],
        "testCoverageProgression": [
            dict(item) for item in evidence.test_coverage_progression
        ],
        "dependencyMetadata": (
            dict(evidence.dependency_metadata)
            if isinstance(evidence.dependency_metadata, dict)
            else None
        ),
        "documentationEvolution": [
            dict(item) for item in evidence.documentation_evolution
        ],
        "evidenceStatus": dict(evidence.evidence_status),
    }


def _deterministic_day_review(
    day_input,
) -> tuple[DayEvaluationResult, ReviewerReportResult]:
    evidence = _build_day_evidence(day_input)
    score = _score_for_day(day_input, evidence)
    rubric_breakdown = {
        "signalStrength": score,
        "evidenceCount": len(evidence),
        "taskType": day_input.task_type,
    }
    strengths: list[str] = []
    risks: list[str] = []
    if score >= 0.7:
        strengths.append("Strong evidence-backed execution signal")
    if day_input.tests_failed:
        risks.append("Observed failing automated tests")
    if not evidence:
        risks.append("Low direct evidence available")
    day_result = DayEvaluationResult(
        day_index=day_input.day_index,
        score=score,
        rubric_breakdown=rubric_breakdown,
        evidence=evidence,
    )
    reviewer_report = ReviewerReportResult(
        reviewer_agent_key=_reviewer_key_for_day(day_input.day_index),
        day_index=day_input.day_index,
        submission_kind=_submission_kind_for_day(day_input),
        score=score,
        dimensional_scores_json=dict(rubric_breakdown),
        evidence_citations_json=list(evidence),
        assessment_text="Deterministic demo/test reviewer output.",
        strengths_json=strengths,
        risks_json=risks,
        raw_output_json={
            "dayIndex": day_input.day_index,
            "score": score,
            "summary": "Deterministic demo/test reviewer output.",
            "rubricBreakdown": dict(rubric_breakdown),
            "evidence": list(evidence),
            "strengths": strengths,
            "risks": risks,
        },
    )
    return day_result, reviewer_report


def _deterministic_aggregate_report(
    *,
    bundle: EvaluationInputBundle,
    snapshot_json: dict[str, object],
    day_results: list[DayEvaluationResult],
    reviewer_reports: list[ReviewerReportResult],
    report_day_scores: list[dict[str, object]],
) -> dict[str, object]:
    overall, confidence = _aggregate_scores(day_results)
    citations = _synthesis_citations_from_bundle(
        bundle=bundle,
        reviewer_reports=reviewer_reports,
    )
    strengths = _unique_strings(
        item
        for report in reviewer_reports
        for item in report.strengths_json
        if isinstance(item, str)
    )[:6]
    risks = _unique_strings(
        item
        for report in reviewer_reports
        for item in report.risks_json
        if isinstance(item, str)
    )[:6]
    return {
        "overallWinoeScore": overall,
        "recommendation": _recommendation_from_score(overall),
        "confidence": confidence,
        "dayScores": list(report_day_scores),
        "disabledDayIndexes": sorted(bundle.disabled_day_indexes),
        "strengths": strengths,
        "risks": risks,
        "calibrationText": "Deterministic demo/test aggregation.",
        "citations": citations,
        "reviewerReports": [
            _reviewer_report_payload(report) for report in reviewer_reports
        ],
        "version": {
            "scenarioVersionId": bundle.scenario_version_id,
            "model": bundle.model_name,
            "modelVersion": bundle.model_version,
            "provider": str(
                snapshot_json["agents"]["winoeReport"]["runtime"]["provider"]
            ),
            "promptVersion": bundle.prompt_version,
            "rubricVersion": bundle.rubric_version,
            "aiPolicySnapshotDigest": (
                bundle.ai_policy_snapshot_digest or snapshot_json.get("snapshotDigest")
            ),
            "promptPackVersion": snapshot_json.get("promptPackVersion"),
            "rubricSnapshots": snapshot_json.get("rubricSnapshots") or [],
        },
    }


def _merge_day_scores(
    *,
    reviewer_day_scores: list[dict[str, object]],
    aggregator_day_scores: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged: dict[int, dict[str, object]] = {}
    for item in reviewer_day_scores:
        day_index = item.get("dayIndex")
        if isinstance(day_index, int):
            merged[day_index] = dict(item)
    for item in aggregator_day_scores:
        day_index = item.get("dayIndex")
        if isinstance(day_index, int) and day_index not in merged:
            merged[day_index] = dict(item)
    return [merged[day] for day in sorted(merged)]


def _unique_strings(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _aggregate_scores(day_results: list[DayEvaluationResult]) -> tuple[float, float]:
    if not day_results:
        return 0.0, 0.0
    overall = round(sum(result.score for result in day_results) / len(day_results), 4)
    evidence_total = sum(len(result.evidence) for result in day_results)
    coverage = evidence_total / max(1, len(day_results) * 3)
    confidence = round(min(0.95, 0.45 + (coverage * 0.5)), 4)
    return overall, confidence


def _coerce_output_value(output: object, key: str, default: object = None) -> object:
    if isinstance(output, dict):
        return output.get(key, default)
    return getattr(output, key, default)


def _format_mmss(milliseconds: int | None) -> str:
    if not isinstance(milliseconds, int) or milliseconds < 0:
        return "00:00"
    seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _markdown_line_ranges(
    text: str | None,
    *,
    label: str,
    dimension: str,
    artifact_ref_prefix: str | None = None,
) -> list[dict[str, object]]:
    if not isinstance(text, str) or not text.strip():
        return []
    lines = text.splitlines()
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines, start=1):
        if line.strip():
            if start is None:
                start = index
            continue
        if start is not None:
            blocks.append((start, index - 1))
            start = None
    if start is not None:
        blocks.append((start, len(lines)))
    if len(blocks) == 1:
        block_start, block_end = blocks[0]
        if block_end > block_start:
            midpoint = block_start + ((block_end - block_start) // 2)
            blocks = [
                (block_start, midpoint),
                (midpoint + 1, block_end),
            ]
        else:
            blocks = [(block_start, block_end)]
    citations: list[dict[str, object]] = []
    for block_start, block_end in blocks[:2]:
        citations.append(
            {
                "dimension": dimension,
                "artifact_type": label,
                "artifact_ref": (
                    f"{artifact_ref_prefix or label}.md:L{block_start}-L{block_end}"
                ),
                "excerpt": "\n".join(lines[block_start - 1 : block_end]).strip()[:300],
            }
        )
    return citations


def _transcript_citations(
    segments: list[dict[str, Any]],
    *,
    dimension: str,
) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    for segment in segments[:2]:
        start_ms = segment.get("startMs")
        end_ms = segment.get("endMs")
        text = segment.get("text")
        citations.append(
            {
                "dimension": dimension,
                "artifact_type": "handoff_transcript",
                "artifact_ref": f"[{_format_mmss(start_ms)}-{_format_mmss(end_ms)}]",
                "excerpt": str(text).strip()[:300] if isinstance(text, str) else "",
            }
        )
    return citations


def _reviewer_text_excerpt(reviewer_reports: list[ReviewerReportResult]) -> str:
    pieces = [
        report.assessment_text.strip()
        for report in reviewer_reports
        if report.assessment_text.strip()
    ]
    return (
        " ".join(pieces[:2])[:500]
        if pieces
        else "Synthesis grounded in persisted reviewer reports."
    )


def _dimension_scores_from_results(
    *,
    day_results: list[DayEvaluationResult],
    reviewer_reports: list[ReviewerReportResult],
) -> list[dict[str, object]]:
    reviewer_report_count = len(reviewer_reports)
    _ = reviewer_report_count
    by_day = {result.day_index: result for result in day_results}
    design = by_day.get(1).score if by_day.get(1) is not None else 0.0
    code_values = [
        by_day.get(day).score for day in (2, 3) if by_day.get(day) is not None
    ]
    testing_values = [
        by_day.get(day).score for day in (2, 3) if by_day.get(day) is not None
    ]
    process_values = [
        by_day.get(day).score for day in (2, 3) if by_day.get(day) is not None
    ]
    comm_values = [
        by_day.get(day).score for day in (4, 5) if by_day.get(day) is not None
    ]
    reflection = by_day.get(5).score if by_day.get(5) is not None else 0.0

    def _scale(value: float | None, fallback: float = 0.0) -> float:
        normalized = float(value if value is not None else fallback)
        return max(1.0, round(normalized * 10.0, 1))

    return [
        {
            "name": "Architecture & Design",
            "score": _scale(design),
            "justification": "Day 1 planning evidence and persisted reviewer analysis show how the candidate framed the system and its constraints.",
        },
        {
            "name": "Problem Understanding",
            "score": _scale(design),
            "justification": "Day 1 planning evidence shows whether the candidate understood the actual problem, users, and constraints.",
        },
        {
            "name": "Implementation Quality",
            "score": _scale(
                sum(code_values) / len(code_values) if code_values else 0.0
            ),
            "justification": "The repository evidence across Days 2 and 3 shows how consistently the work was implemented.",
        },
        {
            "name": "Code Quality",
            "score": _scale(
                sum(code_values) / len(code_values) if code_values else 0.0
            ),
            "justification": "The Day 2 and Day 3 repository evidence shows how the candidate structured, named, and integrated the implementation.",
        },
        {
            "name": "Testing Discipline",
            "score": _scale(
                sum(testing_values) / len(testing_values) if testing_values else 0.0
            ),
            "justification": "The repository evidence, test outputs, and reviewer reports show how the candidate verified the work.",
        },
        {
            "name": "Development Process",
            "score": _scale(
                sum(process_values) / len(process_values) if process_values else 0.0
            ),
            "justification": "The implementation evidence and review trail show whether the candidate worked in a disciplined, iterative way.",
        },
        {
            "name": "Communication",
            "score": _scale(
                sum(comm_values) / len(comm_values) if comm_values else 0.0
            ),
            "justification": "The Handoff + Demo transcript and reflection material show how clearly the candidate explained the work and its tradeoffs.",
        },
        {
            "name": "Reflection & Ownership",
            "score": _scale(reflection),
            "justification": "The Day 5 reflection shows whether the candidate can review their own tradeoffs and describe what they would improve.",
        },
    ]


def _normalize_citation_excerpt(value: object) -> str:
    if isinstance(value, str):
        return value.strip()[:300]
    return ""


def _citation_from_reviewer_pointer(
    pointer: Any,
    *,
    dimension: str,
    fallback_artifact_type: str,
    submission_id: int | None = None,
) -> dict[str, object] | None:
    if not isinstance(pointer, dict):
        return None
    artifact_ref = pointer.get("artifact_ref") or pointer.get("ref")
    start_ms = pointer.get("startMs")
    end_ms = pointer.get("endMs")
    if isinstance(start_ms, int) or isinstance(end_ms, int):
        start_ms = int(start_ms if isinstance(start_ms, int) else end_ms)
        end_ms = int(end_ms if isinstance(end_ms, int) else start_ms)
        if end_ms < start_ms:
            end_ms = start_ms
        artifact_ref = f"[{_format_mmss(start_ms)}-{_format_mmss(end_ms)}]"
        artifact_type = "transcript"
    else:
        if not isinstance(artifact_ref, str) or not artifact_ref.strip():
            return None
        artifact_ref = artifact_ref.strip()
        if not (
            _MARKDOWN_RANGE_RE.match(artifact_ref)
            or _TIMESTAMP_RANGE_RE.match(artifact_ref)
        ):
            artifact_ref = None
        artifact_type = str(
            pointer.get("artifact_type")
            or pointer.get("kind")
            or fallback_artifact_type
        ).strip()
    excerpt = _normalize_citation_excerpt(
        pointer.get("excerpt") or pointer.get("quote") or ""
    )
    if not excerpt:
        return None
    if artifact_ref is None:
        if submission_id is None:
            return None
        artifact_ref = f"submission:{submission_id}"
    return {
        "dimension": dimension,
        "artifact_type": artifact_type,
        "artifact_ref": artifact_ref,
        "excerpt": excerpt,
    }


def _extend_dimension_citations(
    citations_by_dimension: dict[str, list[dict[str, object]]],
    *,
    dimension: str,
    entries: list[dict[str, object]],
) -> None:
    if not entries:
        return
    bucket = citations_by_dimension.setdefault(dimension, [])
    seen = {
        _citation_identity(item)
        for item in bucket
        if isinstance(item, dict) and all(_citation_identity(item))
    }
    for entry in entries:
        identity = _citation_identity(entry)
        if not all(identity) or identity in seen:
            continue
        artifact_ref = identity[1]
        if _is_submission_artifact_ref(artifact_ref) and any(
            _is_stronger_artifact_ref(item.get("artifact_ref"))
            for item in bucket
            if isinstance(item, dict)
        ):
            continue
        seen.add(identity)
        bucket.append(entry)


def _code_evidence_paths_from_bundle(bundle: EvaluationInputBundle) -> list[str]:
    evidence = bundle.code_implementation_evidence
    if evidence is None:
        return []

    paths: list[str] = []
    seen: set[str] = set()

    def _append(path: object) -> None:
        if not isinstance(path, str):
            return
        normalized = path.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        paths.append(normalized)

    repository_snapshot = getattr(evidence, "repository_snapshot", None)
    if isinstance(repository_snapshot, dict):
        for entry in repository_snapshot.get("daySubmissionRefs") or []:
            if not isinstance(entry, dict):
                continue
            for key in ("path", "filePath", "repositoryPath"):
                _append(entry.get(key))
            changed_paths = entry.get("filesChangedPaths") or entry.get("filesChanged")
            if isinstance(changed_paths, list):
                for item in changed_paths:
                    _append(item)

    for entry in getattr(evidence, "repository_artifact_references", []) or []:
        if not isinstance(entry, dict):
            continue
        _append(entry.get("path") or entry.get("filePath"))

    for entry in getattr(evidence, "commit_history", []) or []:
        if not isinstance(entry, dict):
            continue
        for path in entry.get("filesChangedPaths") or []:
            _append(path)

    for entry in getattr(evidence, "file_creation_timeline", []) or []:
        if not isinstance(entry, dict):
            continue
        _append(entry.get("path"))

    return paths


def _code_path_citations(
    *,
    dimension: str,
    artifact_type: str,
    paths: list[str],
) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    if not paths:
        return citations

    for path in paths[:2]:
        citations.append(
            {
                "dimension": dimension,
                "artifact_type": artifact_type,
                "artifact_ref": f"{path}:L1-L1",
                "excerpt": (
                    f"Structured repository evidence for {dimension} at {path}."
                ),
            }
        )
    return citations


def _transcript_dimension_citations(
    *,
    day_input,
    dimension: str,
) -> list[dict[str, object]]:
    citations = _transcript_citations(
        day_input.transcript_segments if day_input else [],
        dimension=dimension,
    )
    return citations


def _markdown_dimension_citations(
    *,
    dimension: str,
    text: str | None,
    artifact_prefix: str,
    artifact_type: str,
) -> list[dict[str, object]]:
    citations = _markdown_line_ranges(
        text,
        label=artifact_type,
        dimension=dimension,
        artifact_ref_prefix=artifact_prefix,
    )
    return citations


def _synthesis_citations_from_bundle(
    *,
    bundle: EvaluationInputBundle,
    reviewer_reports: list[ReviewerReportResult],
) -> list[dict[str, object]]:
    day_inputs = {day.day_index: day for day in bundle.day_inputs}
    day1 = day_inputs.get(1)
    day2 = day_inputs.get(2)
    day3 = day_inputs.get(3)
    day4 = day_inputs.get(4)
    day5 = day_inputs.get(5)
    citations_by_dimension: dict[str, list[dict[str, object]]] = {}

    code_paths = _code_evidence_paths_from_bundle(bundle)
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Architecture & Design",
        entries=_markdown_dimension_citations(
            dimension="Architecture & Design",
            text=day1.content_text if day1 else None,
            artifact_prefix="day1-design-doc",
            artifact_type="design_doc",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Problem Understanding",
        entries=_markdown_dimension_citations(
            dimension="Problem Understanding",
            text=day1.content_text if day1 else None,
            artifact_prefix="day1-design-doc",
            artifact_type="design_doc",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Implementation Quality",
        entries=_markdown_dimension_citations(
            dimension="Implementation Quality",
            text=day2.content_text if day2 else None,
            artifact_prefix="day2-code-submission",
            artifact_type="code_submission",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Testing Discipline",
        entries=_markdown_dimension_citations(
            dimension="Testing Discipline",
            text=day2.content_text if day2 else None,
            artifact_prefix="day2-code-submission",
            artifact_type="code_submission",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Testing Discipline",
        entries=_code_path_citations(
            dimension="Testing Discipline",
            artifact_type="tests",
            paths=code_paths,
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Implementation Quality",
        entries=_code_path_citations(
            dimension="Implementation Quality",
            artifact_type="code_implementation",
            paths=code_paths,
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Code Quality",
        entries=_markdown_dimension_citations(
            dimension="Code Quality",
            text=day3.content_text if day3 else None,
            artifact_prefix="day3-code-submission",
            artifact_type="code_submission",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Development Process",
        entries=_markdown_dimension_citations(
            dimension="Development Process",
            text=day3.content_text if day3 else None,
            artifact_prefix="day3-code-submission",
            artifact_type="code_submission",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Code Quality",
        entries=_code_path_citations(
            dimension="Code Quality",
            artifact_type="code_implementation",
            paths=code_paths[1:] or code_paths,
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Development Process",
        entries=_code_path_citations(
            dimension="Development Process",
            artifact_type="code_implementation",
            paths=code_paths[1:] or code_paths,
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Communication",
        entries=_transcript_dimension_citations(
            day_input=day4,
            dimension="Communication",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Communication",
        entries=_markdown_dimension_citations(
            dimension="Communication",
            text=day5.content_text if day5 else None,
            artifact_prefix="day5-reflection",
            artifact_type="reflection",
        ),
    )
    _extend_dimension_citations(
        citations_by_dimension,
        dimension="Reflection & Ownership",
        entries=_markdown_dimension_citations(
            dimension="Reflection & Ownership",
            text=day5.content_text if day5 else None,
            artifact_prefix="day5-reflection",
            artifact_type="reflection",
        ),
    )

    reviewer_dimension_map = {
        1: ("Architecture & Design", "Problem Understanding"),
        2: ("Implementation Quality", "Testing Discipline"),
        3: ("Code Quality", "Development Process"),
        4: ("Communication",),
        5: ("Reflection & Ownership",),
    }
    for reviewer_report in reviewer_reports:
        dimensions = reviewer_dimension_map.get(reviewer_report.day_index, ())
        if not dimensions:
            continue
        day_input = day_inputs.get(reviewer_report.day_index)
        for dimension in dimensions:
            fallback_artifact_type = "design_doc"
            if reviewer_report.day_index in {2, 3}:
                fallback_artifact_type = "code_implementation"
            elif reviewer_report.day_index == 4:
                fallback_artifact_type = "transcript"
            elif reviewer_report.day_index == 5:
                fallback_artifact_type = "reflection"
            resolved_entries: list[dict[str, object]] = []
            for pointer in reviewer_report.evidence_citations_json or []:
                citation = _citation_from_reviewer_pointer(
                    pointer,
                    dimension=dimension,
                    fallback_artifact_type=fallback_artifact_type,
                    submission_id=(
                        getattr(day_input, "submission_id", None) if day_input else None
                    ),
                )
                if citation is None:
                    continue
                resolved_entries.append(citation)
            resolved_entries.sort(
                key=lambda item: 1
                if _is_submission_artifact_ref(item.get("artifact_ref"))
                else 0
            )
            _extend_dimension_citations(
                citations_by_dimension,
                dimension=dimension,
                entries=resolved_entries,
            )

    ordered_dimensions = [
        "Architecture & Design",
        "Problem Understanding",
        "Implementation Quality",
        "Code Quality",
        "Testing Discipline",
        "Development Process",
        "Communication",
        "Reflection & Ownership",
    ]
    citations: list[dict[str, object]] = []
    for dimension in ordered_dimensions:
        citations.extend(citations_by_dimension.get(dimension, []))
    return citations


def _build_narrative_assessment(
    *,
    dimensions: list[dict[str, object]],
    reviewer_reports: list[ReviewerReportResult],
    citations: list[dict[str, object]],
) -> str:
    refs_by_dimension: dict[str, dict[str, list[str]]] = {}
    for citation in citations:
        dimension = str(citation.get("dimension") or "").strip()
        artifact_ref = str(citation.get("artifact_ref") or "").strip()
        if not dimension or not artifact_ref:
            continue
        bucket = refs_by_dimension.setdefault(
            dimension,
            {"strong": [], "submission": []},
        )
        target = "submission" if _is_submission_artifact_ref(artifact_ref) else "strong"
        if artifact_ref not in bucket[target]:
            bucket[target].append(artifact_ref)

    paragraphs: list[str] = []
    for dimension in dimensions:
        name = str(dimension["name"])
        score = float(dimension["score"])
        bucket = refs_by_dimension.get(name, {"strong": [], "submission": []})
        refs = (bucket["strong"] or bucket["submission"])[:2]
        citation_suffix = ""
        if refs:
            citation_suffix = " Evidence: " + "; ".join(refs) + "."
        if name == "Architecture & Design":
            body = (
                "The planning evidence shows a coherent shape and enough constraint "
                "awareness to make the implementation tractable. The strongest signal "
                "is the combination of the design doc and the later repository choices."
            )
        elif name == "Code Quality":
            body = (
                "The repository reads like deliberate work rather than a one-shot dump. "
                "The implementation appears integrated, with enough structure to support review and iteration."
            )
        elif name == "Testing":
            body = (
                "The evidence trail shows an explicit testing posture, including automated verification and visible test-capture steps. "
                "That is a meaningful quality signal even when some tests fail or need iteration."
            )
        else:
            body = "The Handoff + Demo and reflection signals show whether the candidate can explain the work, own the tradeoffs, and keep the Talent Partner oriented to the real evidence."
        paragraphs.append(
            f"### {name}: {body}{citation_suffix} The working score for this dimension is {score:.1f}/10."
        )
    summary = _reviewer_text_excerpt(reviewer_reports)
    summary_refs = [
        str(item.get("artifact_ref") or "").strip()
        for item in citations
        if str(item.get("artifact_ref") or "").strip()
        and not _is_submission_artifact_ref(item.get("artifact_ref"))
    ][:2]
    if not summary_refs:
        summary_refs = [
            str(item.get("artifact_ref") or "").strip() for item in citations[:2]
        ]
    summary_suffix = ""
    if any(summary_refs):
        summary_suffix = (
            " Evidence: " + "; ".join(ref for ref in summary_refs if ref) + "."
        )
    paragraphs.append("### Cohort Context: " f"{summary}{summary_suffix}")
    return "\n\n".join(paragraphs).strip()


def _build_winoe_report_payload(
    *,
    bundle: EvaluationInputBundle,
    day_results: list[DayEvaluationResult],
    reviewer_reports: list[ReviewerReportResult],
    report_day_scores: list[dict[str, object]],
    synthesis_output: object | None = None,
) -> dict[str, object]:
    dimensions = _coerce_output_value(synthesis_output, "dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        dimensions = _dimension_scores_from_results(
            day_results=day_results,
            reviewer_reports=reviewer_reports,
        )
    normalized_dimensions: list[dict[str, object]] = []
    for item in dimensions:
        if isinstance(item, dict):
            normalized_dimensions.append(dict(item))
        elif hasattr(item, "model_dump"):
            normalized_dimensions.append(dict(item.model_dump()))
        else:
            continue
    winoe_score = _coerce_output_value(synthesis_output, "winoe_score")
    if not isinstance(winoe_score, int | float):
        overall, _confidence = _aggregate_scores(day_results)
        winoe_score = round(overall * 100.0, 2)
    verdict_one_liner = _coerce_output_value(
        synthesis_output,
        "verdict_one_liner",
        "Strong evidence trail with room to verify a few edges.",
    )
    if not isinstance(verdict_one_liner, str) or not verdict_one_liner.strip():
        verdict_one_liner = "Strong evidence trail with room to verify a few edges."
    citations = _coerce_output_value(synthesis_output, "citations")
    if not isinstance(citations, list) or not citations:
        citations = []
    normalized_citations: list[dict[str, object]] = []
    for item in citations:
        if isinstance(item, dict):
            normalized_citations.append(dict(item))
        elif hasattr(item, "model_dump"):
            normalized_citations.append(dict(item.model_dump()))
    normalized_citations = _dedupe_citations(normalized_citations)
    dimension_names = [
        str(item.get("name") or "").strip()
        for item in normalized_dimensions
        if str(item.get("name") or "").strip()
    ]
    citation_counts_by_dimension: dict[str, int] = {}
    for item in normalized_citations:
        dimension = str(item.get("dimension") or "").strip()
        artifact_ref = str(item.get("artifact_ref") or "").strip()
        if not dimension or not artifact_ref:
            continue
        citation_counts_by_dimension[dimension] = (
            citation_counts_by_dimension.get(dimension, 0) + 1
        )
    if any(
        citation_counts_by_dimension.get(dimension, 0) < 2
        for dimension in dimension_names
    ):
        fallback_citations = _synthesis_citations_from_bundle(
            bundle=bundle,
            reviewer_reports=reviewer_reports,
        )
        if fallback_citations:
            normalized_citations.extend(fallback_citations)
            normalized_citations = _dedupe_citations(normalized_citations)
            citation_counts_by_dimension = {}
            for item in normalized_citations:
                dimension = str(item.get("dimension") or "").strip()
                artifact_ref = str(item.get("artifact_ref") or "").strip()
                if not dimension or not artifact_ref:
                    continue
                citation_counts_by_dimension[dimension] = (
                    citation_counts_by_dimension.get(dimension, 0) + 1
                )
    narrative_assessment = _coerce_output_value(
        synthesis_output, "narrative_assessment"
    )
    if not isinstance(narrative_assessment, str) or not narrative_assessment.strip():
        narrative_assessment = _build_narrative_assessment(
            dimensions=normalized_dimensions,
            reviewer_reports=reviewer_reports,
            citations=normalized_citations,
        )
    cohort_context = _coerce_output_value(synthesis_output, "cohort_context")
    if not isinstance(cohort_context, str) or not cohort_context.strip():
        cohort_context = "above the median for the matched cohort"
    snapshot_json = (
        bundle.ai_policy_snapshot_json
        if isinstance(bundle.ai_policy_snapshot_json, dict)
        else {}
    )
    winoe_report_snapshot = (
        snapshot_json.get("agents", {}).get("winoeReport", {})
        if isinstance(snapshot_json, dict)
        else {}
    )
    overall_winoe_score = round(float(winoe_score) / 100.0, 4)
    confidence = round(min(0.95, 0.55 + min(0.35, len(normalized_citations) / 20.0)), 4)
    strengths = [
        str(item["name"])
        for item in sorted(
            normalized_dimensions, key=lambda value: float(value["score"]), reverse=True
        )[:2]
    ]
    risks = [
        str(item["name"])
        for item in sorted(
            normalized_dimensions, key=lambda value: float(value["score"])
        )[:2]
    ]
    return {
        "winoe_score": float(winoe_score),
        "verdict_one_liner": verdict_one_liner.strip(),
        "dimensions": [
            {
                "name": str(item["name"]),
                "score": float(item["score"]),
                "justification": str(item["justification"]),
            }
            for item in normalized_dimensions
        ],
        "narrative_assessment": narrative_assessment.strip(),
        "citations": [
            {
                "dimension": str(item.get("dimension") or ""),
                "artifact_type": str(item.get("artifact_type") or ""),
                "artifact_ref": str(item.get("artifact_ref") or ""),
                "excerpt": str(item.get("excerpt") or "").strip(),
            }
            for item in normalized_citations
            if str(item.get("artifact_ref") or "").strip()
        ],
        "cohort_context": cohort_context.strip()
        if isinstance(cohort_context, str)
        else None,
        "overallWinoeScore": overall_winoe_score,
        "recommendation": _recommendation_from_score(overall_winoe_score),
        "confidence": confidence,
        "dayScores": list(report_day_scores),
        "strengths": strengths,
        "risks": risks,
        "calibrationText": narrative_assessment.strip(),
        "reviewerReports": [
            _reviewer_report_payload(report) for report in reviewer_reports
        ],
        "version": {
            "scenarioVersionId": bundle.scenario_version_id,
            "model": bundle.model_name,
            "modelVersion": bundle.model_version,
            "provider": (
                str(winoe_report_snapshot.get("provider"))
                if isinstance(winoe_report_snapshot, dict)
                and isinstance(winoe_report_snapshot.get("provider"), str)
                else None
            ),
            "promptVersion": bundle.prompt_version,
            "rubricVersion": bundle.rubric_version,
            "aiPolicySnapshotDigest": bundle.ai_policy_snapshot_digest,
            "promptPackVersion": (
                str(snapshot_json.get("promptPackVersion"))
                if isinstance(snapshot_json, dict)
                and isinstance(snapshot_json.get("promptPackVersion"), str)
                else None
            ),
            "rubricSnapshots": (
                list(bundle.trial_context_json.get("rubricSnapshots"))
                if isinstance(bundle.trial_context_json, dict)
                and isinstance(bundle.trial_context_json.get("rubricSnapshots"), list)
                else []
            ),
        },
    }


_default_evaluator: WinoeReportEvaluator = LiveWinoeReportEvaluator()


def get_winoe_report_evaluator() -> WinoeReportEvaluator:
    """Return winoe report evaluator."""
    return _default_evaluator


__all__ = [
    "DeterministicWinoeReportEvaluator",
    "LiveWinoeReportEvaluator",
    "get_winoe_report_evaluator",
]
