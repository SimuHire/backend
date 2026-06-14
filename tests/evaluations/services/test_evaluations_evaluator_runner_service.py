from __future__ import annotations

import json
import re
from dataclasses import fields
from types import SimpleNamespace

import pytest

from app.ai import (
    AIPolicySnapshotError,
    build_ai_policy_snapshot,
    compute_ai_policy_snapshot_basis_fingerprint,
    compute_ai_policy_snapshot_digest,
)
from app.ai.ai_provider_clients_service import AIProviderExecutionError
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RECOMMENDATION_NO_HIRE,
)
from app.evaluations.services import (
    evaluations_services_evaluations_evaluator_runtime_service as evaluator_runtime,
)
from app.evaluations.services import (
    evaluations_services_evaluations_winoe_report_pipeline_day_inputs_service as day_inputs_service,
)
from app.evaluations.services import (
    evaluations_services_evaluations_winoe_report_pipeline_runner_service as winoe_report_runner,
)
from app.evaluations.services import evaluator
from app.evaluations.services.evaluations_services_evaluations_evaluator_models_service import (
    CodeImplementationEvidenceContext,
    DayEvaluationResult,
    ReviewerReportResult,
)
from app.integrations.winoe_report_review import (
    anthropic_provider_client as winoe_anthropic_provider,
)
from app.integrations.winoe_report_review import (
    openai_provider_client as winoe_openai_provider,
)
from tests.evaluations.services.evaluations_evaluator_branch_gap_utils import day_input
from tests.evaluations.services.evaluations_winoe_report_fixtures_utils import (
    build_valid_winoe_report_json,
)
from tests.shared.factories import build_trial_agent_snapshots


def _snapshot():
    trial = SimpleNamespace(
        ai_notice_version="mvp1",
        ai_notice_text="AI assistance may be used for evaluation support.",
        ai_eval_enabled_by_day={"1": True, "2": True, "3": True, "4": True, "5": True},
        agent_snapshots=build_trial_agent_snapshots(),
    )
    return build_ai_policy_snapshot(trial=trial)


async def test_deterministic_evaluator_handles_empty_enabled_days():
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=1,
        scenario_version_id=2,
        model_name="model-x",
        model_version="v1",
        prompt_version="p1",
        rubric_version="r1",
        disabled_day_indexes=[1],
        day_inputs=[day_input(day_index=1, content_text="text")],
        ai_policy_snapshot_json=_snapshot(),
    )
    result = await evaluator.DeterministicWinoeReportEvaluator().evaluate(bundle)
    assert result.overall_winoe_score == 0.0
    assert result.confidence > 0.0
    assert result.recommendation == EVALUATION_RECOMMENDATION_NO_HIRE
    assert result.day_results == []
    assert result.reviewer_reports == []
    assert result.report_json["dayScores"] == [
        {
            "dayIndex": 1,
            "status": "human_review_required",
            "reason": "ai_eval_disabled_for_day",
        }
    ]
    assert result.report_json["citations"]


async def test_deterministic_evaluator_sorts_days_and_builds_report():
    snapshot = _snapshot()
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="model-y",
        model_version="v2",
        prompt_version="p2",
        rubric_version="r2",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=5, content_text="final reflection"),
            day_input(
                day_index=2,
                repo_full_name="acme/repo",
                cutoff_commit_sha="cutoff-sha",
                diff_summary={"base": "a", "head": "b"},
                tests_passed=4,
                tests_failed=0,
                workflow_run_id="555",
            ),
        ],
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
    )
    result = await evaluator.get_winoe_report_evaluator().evaluate(bundle)
    assert [day.day_index for day in result.day_results] == [2, 5]
    assert [report.day_index for report in result.reviewer_reports] == [2, 5]
    assert [report.reviewer_agent_key for report in result.reviewer_reports] == [
        "codeImplementationReviewer",
        "reflectionEssayReviewer",
    ]
    assert 0 <= result.overall_winoe_score <= 1
    assert 0 <= result.confidence <= 1
    assert result.report_json["version"]["modelVersion"] == "v2"
    assert result.report_json["version"]["provider"] is not None
    assert result.report_json["version"]["aiPolicySnapshotDigest"] is not None
    assert result.report_json["dayScores"][0]["dayIndex"] == 2


async def test_live_evaluator_requires_snapshot():
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="model-y",
        model_version="v2",
        prompt_version="p2",
        rubric_version="r2",
        disabled_day_indexes=[],
        day_inputs=[day_input(day_index=5, content_text="final reflection")],
    )
    with pytest.raises(
        AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_missing",
    ):
        await evaluator.get_winoe_report_evaluator().evaluate(bundle)


async def test_deterministic_evaluator_requires_snapshot():
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="model-y",
        model_version="v2",
        prompt_version="p2",
        rubric_version="r2",
        disabled_day_indexes=[],
        day_inputs=[day_input(day_index=1, content_text="text")],
    )
    with pytest.raises(
        AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_missing",
    ):
        await evaluator.DeterministicWinoeReportEvaluator().evaluate(bundle)


async def test_live_evaluator_rejects_snapshot_contract_mismatch():
    snapshot = _snapshot()
    snapshot["agents"]["codespace"] = {
        "key": "codespace",
        "promptVersion": "legacy",
        "rubricVersion": "legacy",
        "runtime": {
            "runtimeMode": "test",
            "provider": "openai",
            "model": "gpt-4.1",
        },
    }
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="model-y",
        model_version="v2",
        prompt_version="p2",
        rubric_version="r2",
        disabled_day_indexes=[],
        day_inputs=[day_input(day_index=1, content_text="text")],
        ai_policy_snapshot_json=snapshot,
    )
    with pytest.raises(
        AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_agent_contract_mismatch",
    ):
        await evaluator.get_winoe_report_evaluator().evaluate(bundle)


@pytest.mark.asyncio
async def test_live_evaluator_falls_back_once_and_completes(
    monkeypatch,
):
    snapshot = _snapshot()
    for agent in snapshot["agents"].values():
        agent["runtime"]["runtimeMode"] = "real"
    snapshot["snapshotDigest"] = compute_ai_policy_snapshot_basis_fingerprint(snapshot)
    day1_text = "\n".join(f"design line {index}" for index in range(1, 9))
    day2_text = "\n".join(f"implementation line {index}" for index in range(1, 9))
    day3_text = "\n".join(f"code quality line {index}" for index in range(1, 9))
    day5_text = "\n".join(f"reflection line {index}" for index in range(1, 9))
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="winoe-ai-pack-v4:winoeReport",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=1, content_text=day1_text),
            day_input(
                day_index=2,
                content_text=day2_text,
                repo_full_name="acme/repo",
                commit_sha="abc1234",
                cutoff_commit_sha="cutoff-day2-fixed",
                diff_summary={"base": "base", "head": "head"},
                tests_passed=3,
                tests_failed=0,
            ),
            day_input(
                day_index=3,
                content_text=day3_text,
                repo_full_name="acme/repo",
                commit_sha="def5678",
                cutoff_commit_sha="cutoff-day3-fixed",
                diff_summary={"base": "base", "head": "head"},
                tests_passed=4,
                tests_failed=0,
            ),
            day_input(
                day_index=4,
                transcript_segments=[
                    {"startMs": 120000, "endMs": 128000, "text": "Handoff walkthrough"},
                    {"startMs": 128000, "endMs": 136000, "text": "Evidence summary"},
                ],
            ),
            day_input(day_index=5, content_text=day5_text),
        ],
        code_implementation_evidence=CodeImplementationEvidenceContext(
            repository_snapshot={
                "daySubmissionRefs": [
                    {"commitSha": "abc1234"},
                    {"commitSha": "def5678"},
                ]
            },
            commit_history=[
                {"sha": "abc1234", "filesChangedPaths": ["src/a.ts"]},
                {"sha": "def5678", "filesChangedPaths": ["src/b.ts"]},
            ],
            file_creation_timeline=[
                {"path": "src/a.ts"},
                {"path": "src/b.ts"},
            ],
        ),
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
        trial_context_json={"trialId": 1, "title": "Demo Trial"},
    )
    calls: list[tuple[str, str, str]] = []
    failed_once = False

    def _reviewer_output(day_index: int):
        return {
            "dayIndex": day_index,
            "score": 0.8,
            "summary": f"Day {day_index} stayed evidence-backed.",
            "rubricBreakdown": {"signal": 0.8},
            "evidence": [],
            "strengths": ["Clear signal"],
            "risks": ["Minor follow-up"],
        }

    def _extract_day_index(prompt: str) -> int:
        match = re.search(r'"dayIndex"\s*:\s*(\d+)', prompt)
        return int(match.group(1)) if match is not None else 2

    def _fake_openai_json_schema(**kwargs):
        nonlocal failed_once
        calls.append(("openai", kwargs["model"], kwargs["response_model"].__name__))
        if kwargs["response_model"].__name__ == "DayReviewerOutput":
            if not failed_once:
                failed_once = True
                raise AIProviderExecutionError("openai_request_failed:RateLimitError")
            return kwargs["response_model"].model_validate(
                _reviewer_output(_extract_day_index(kwargs["user_prompt"]))
            )
        return kwargs["response_model"].model_validate(build_valid_winoe_report_json())

    def _fake_anthropic_json(**kwargs):
        calls.append(("anthropic", kwargs["model"], kwargs["response_model"].__name__))
        if kwargs["response_model"].__name__ == "DayReviewerOutput":
            return kwargs["response_model"].model_validate(
                _reviewer_output(_extract_day_index(kwargs["user_prompt"]))
            )
        return kwargs["response_model"].model_validate(build_valid_winoe_report_json())

    monkeypatch.setattr(
        winoe_openai_provider, "call_openai_json_schema", _fake_openai_json_schema
    )
    monkeypatch.setattr(
        winoe_openai_provider, "call_anthropic_json", _fake_anthropic_json
    )
    monkeypatch.setattr(
        winoe_anthropic_provider, "call_anthropic_json", _fake_anthropic_json
    )
    monkeypatch.setattr(
        winoe_anthropic_provider, "call_openai_json_schema", _fake_openai_json_schema
    )

    result = await evaluator.get_winoe_report_evaluator().evaluate(bundle)

    assert result.day_results
    assert result.report_json["citations"]
    assert ("openai", "gpt-5.5", "DayReviewerOutput") in calls
    assert any(entry[0] == "anthropic" for entry in calls)


def test_deterministic_winoe_report_emits_unique_real_citations():
    snapshot = _snapshot()
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="winoe-ai-pack-v4:winoeReport",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(
                day_index=1,
                content_text="# Day 1\n\n- Architecture plan\n- Risk controls",
            ),
            day_input(
                day_index=2,
                content_text="# Day 2\n\n- Implement the service\n- Add tests",
            ),
            day_input(
                day_index=3,
                content_text="# Day 3\n\n- Tighten the implementation\n- Improve tests",
            ),
            day_input(
                day_index=4,
                transcript_segments=[
                    {"startMs": 0, "endMs": 900, "text": "Handoff walkthrough"},
                    {"startMs": 900, "endMs": 1800, "text": "Evidence summary"},
                ],
            ),
            day_input(
                day_index=5,
                content_text="# Day 5\n\nReflection and ownership notes",
            ),
        ],
        code_implementation_evidence=CodeImplementationEvidenceContext(
            repository_snapshot={
                "daySubmissionRefs": [
                    {
                        "path": "app/evaluations/services/example_service.py",
                        "commitSha": "abc1234",
                    }
                ]
            },
            repository_artifact_references=[
                {"path": "app/evaluations/services/example_service.py"},
                {"path": "tests/evaluations/services/example_service_test.py"},
            ],
            commit_history=[
                {"filesChangedPaths": ["app/evaluations/services/example_service.py"]},
                {
                    "filesChangedPaths": [
                        "tests/evaluations/services/example_service_test.py"
                    ]
                },
            ],
            file_creation_timeline=[
                {"path": "app/evaluations/services/example_service.py"},
                {"path": "tests/evaluations/services/example_service_test.py"},
            ],
        ),
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
    )

    report = evaluator_runtime._deterministic_aggregate_report(
        bundle=bundle,
        snapshot_json=snapshot,
        day_results=[
            DayEvaluationResult(
                day_index=1,
                score=0.8,
                rubric_breakdown={"Architecture & Design": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=2,
                score=0.8,
                rubric_breakdown={"Implementation Quality": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=3,
                score=0.8,
                rubric_breakdown={"Code Quality": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=4,
                score=0.8,
                rubric_breakdown={"Communication": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=5,
                score=0.8,
                rubric_breakdown={"Reflection & Ownership": 8},
                evidence=[],
            ),
        ],
        reviewer_reports=[
            ReviewerReportResult(
                reviewer_agent_key="demoPresentationReviewer",
                day_index=4,
                submission_kind="handoff",
                score=0.8,
                dimensional_scores_json={"Communication": 8},
                evidence_citations_json=[
                    {
                        "artifact_ref": "[00:00-00:00:00.900]",
                        "excerpt": "Handoff walkthrough",
                    },
                    {
                        "artifact_ref": "[00:00-00:00:01.800]",
                        "excerpt": "Evidence summary",
                    },
                ],
                assessment_text="Communication was clear.",
                strengths_json=[],
                risks_json=[],
            )
        ],
        report_day_scores=[],
    )

    citation_refs = [
        (item["dimension"], item["artifact_ref"], item["excerpt"])
        for item in report["citations"]
    ]
    assert len(set(citation_refs)) == len(report["citations"])

    citations_by_dimension: dict[str, set[tuple[str, str, str]]] = {}
    for item in report["citations"]:
        citations_by_dimension.setdefault(item["dimension"], set()).add(
            (
                item["dimension"],
                item["artifact_ref"],
                item["excerpt"],
            )
        )

    assert set(citations_by_dimension) == {
        "Architecture & Design",
        "Problem Understanding",
        "Implementation Quality",
        "Code Quality",
        "Testing Discipline",
        "Development Process",
        "Communication",
        "Reflection & Ownership",
    }
    assert all(len(items) >= 2 for items in citations_by_dimension.values())
    assert any(ref[0] == "Communication" for ref in citation_refs)


def test_winoe_report_payload_supplies_real_bundle_citations_when_synthesis_output_is_sparse():
    snapshot = _snapshot()
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="winoe-ai-pack-v4:winoeReport",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(
                day_index=1,
                content_text="# Day 1\n\n- Architecture plan\n- Risk controls",
            ),
            day_input(
                day_index=2,
                content_text="# Day 2\n\n- Implement the service\n- Add tests",
            ),
            day_input(
                day_index=3,
                content_text="# Day 3\n\n- Tighten the implementation\n- Improve tests",
            ),
            day_input(
                day_index=4,
                transcript_segments=[
                    {"startMs": 0, "endMs": 900, "text": "Handoff walkthrough"}
                ],
            ),
            day_input(
                day_index=5,
                content_text="# Day 5\n\nReflection and ownership notes",
            ),
        ],
        code_implementation_evidence=CodeImplementationEvidenceContext(
            repository_snapshot={
                "daySubmissionRefs": [
                    {
                        "path": "app/evaluations/services/example_service.py",
                        "commitSha": "abc1234",
                    }
                ]
            },
            repository_artifact_references=[
                {"path": "app/evaluations/services/example_service.py"},
                {"path": "tests/evaluations/services/example_service_test.py"},
            ],
            commit_history=[
                {"filesChangedPaths": ["app/evaluations/services/example_service.py"]},
                {
                    "filesChangedPaths": [
                        "tests/evaluations/services/example_service_test.py"
                    ]
                },
            ],
            file_creation_timeline=[
                {"path": "app/evaluations/services/example_service.py"},
                {"path": "tests/evaluations/services/example_service_test.py"},
            ],
        ),
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
    )
    reviewer_reports = [
        ReviewerReportResult(
            reviewer_agent_key="demoPresentationReviewer",
            day_index=4,
            submission_kind="handoff",
            score=0.8,
            dimensional_scores_json={"Communication": 8},
            evidence_citations_json=[
                {
                    "artifact_ref": "[00:00-00:00:00.900]",
                    "excerpt": "Handoff walkthrough",
                }
            ],
            assessment_text="Communication was clear.",
            strengths_json=[],
            risks_json=[],
        )
    ]
    payload = evaluator_runtime._build_winoe_report_payload(
        bundle=bundle,
        day_results=[
            DayEvaluationResult(
                day_index=1,
                score=0.8,
                rubric_breakdown={"Architecture & Design": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=2,
                score=0.8,
                rubric_breakdown={"Implementation Quality": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=3,
                score=0.8,
                rubric_breakdown={"Code Quality": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=4,
                score=0.8,
                rubric_breakdown={"Communication": 8},
                evidence=[],
            ),
            DayEvaluationResult(
                day_index=5,
                score=0.8,
                rubric_breakdown={"Reflection & Ownership": 8},
                evidence=[],
            ),
        ],
        reviewer_reports=reviewer_reports,
        report_day_scores=[],
        synthesis_output={
            "winoe_score": 80,
            "recommendation": "hire",
            "confidence": 0.6,
            "dimensions": [
                {
                    "name": "Architecture & Design",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Problem Understanding",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Implementation Quality",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Code Quality",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Testing Discipline",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Development Process",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Communication",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
                {
                    "name": "Reflection & Ownership",
                    "score": 8.0,
                    "justification": "Sparse model citation.",
                },
            ],
            "citations": [
                {
                    "dimension": "Communication",
                    "artifact_type": "transcript",
                    "artifact_ref": "[00:00-00:00:00.900]",
                    "excerpt": "Handoff walkthrough",
                }
            ],
            "narrative_assessment": "Paragraph one. Paragraph two. Paragraph three. Paragraph four. Paragraph five. Paragraph six. Paragraph seven. Paragraph eight.",
            "cohort_context": "Above the median",
        },
    )

    citations = payload["citations"]
    identities = {
        (
            item["dimension"],
            item["artifact_ref"],
            item["excerpt"],
        )
        for item in citations
    }
    assert len(citations) > 1
    assert len(identities) == len(citations)
    communication_refs = [
        item["artifact_ref"]
        for item in citations
        if item["dimension"] == "Communication"
    ]
    assert len(communication_refs) >= 2
    assert any(ref.startswith("day5-reflection.md:") for ref in communication_refs)
    assert (
        "Communication",
        "[00:00-00:00:00.900]",
        "Handoff walkthrough",
    ) in identities
    assert any(item["dimension"] == "Testing Discipline" for item in citations)
    assert any(item["dimension"] == "Development Process" for item in citations)
    assert all(
        not str(item["artifact_ref"]).startswith("submission:") for item in citations
    )


def test_synthesis_citations_prefer_strong_refs_over_submission_fallback():
    snapshot = _snapshot()
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="winoe-ai-pack-v4:winoeReport",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=1, content_text=""),
            day_input(day_index=2, content_text=""),
            day_input(day_index=3, content_text=""),
            day_input(
                day_index=4,
                transcript_segments=[
                    {"startMs": 0, "endMs": 900, "text": "Handoff walkthrough"}
                ],
            ),
            day_input(day_index=5, content_text=""),
        ],
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
    )
    bundle.day_inputs[3].submission_id = 404
    reviewer_reports = [
        ReviewerReportResult(
            reviewer_agent_key="demoPresentationReviewer",
            day_index=4,
            submission_kind="handoff",
            score=0.8,
            dimensional_scores_json={"Communication": 8},
            evidence_citations_json=[
                {
                    "artifact_ref": "submission:404",
                    "excerpt": "Fallback handoff evidence.",
                },
                {
                    "artifact_ref": "[00:00-00:00]",
                    "excerpt": "Handoff walkthrough",
                },
            ],
            assessment_text="Communication was clear.",
            strengths_json=[],
            risks_json=[],
        )
    ]

    citations = evaluator_runtime._synthesis_citations_from_bundle(
        bundle=bundle,
        reviewer_reports=reviewer_reports,
    )
    communication_refs = [
        item["artifact_ref"]
        for item in citations
        if item["dimension"] == "Communication"
    ]

    assert "[00:00-00:00]" in communication_refs
    assert "submission:404" not in communication_refs


def test_synthesis_citations_keep_submission_fallback_when_no_stronger_ref_exists():
    snapshot = _snapshot()
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=10,
        scenario_version_id=20,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="winoe-ai-pack-v4:winoeReport",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=1, content_text=""),
            day_input(day_index=2, content_text=""),
            day_input(day_index=3, content_text=""),
            day_input(day_index=4, content_text=""),
            day_input(day_index=5, content_text=""),
        ],
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
    )
    bundle.day_inputs[3].submission_id = 505
    reviewer_reports = [
        ReviewerReportResult(
            reviewer_agent_key="demoPresentationReviewer",
            day_index=4,
            submission_kind="handoff",
            score=0.8,
            dimensional_scores_json={"Communication": 8},
            evidence_citations_json=[
                {
                    "artifact_ref": "submission:505",
                    "excerpt": "Fallback handoff evidence.",
                }
            ],
            assessment_text="Communication was clear.",
            strengths_json=[],
            risks_json=[],
        )
    ]

    citations = evaluator_runtime._synthesis_citations_from_bundle(
        bundle=bundle,
        reviewer_reports=reviewer_reports,
    )
    communication_refs = [
        item["artifact_ref"]
        for item in citations
        if item["dimension"] == "Communication"
    ]

    assert communication_refs == ["submission:505"]


def test_winoe_report_run_identity_uses_frozen_snapshot_values(monkeypatch):
    snapshot = _snapshot()
    snapshot["promptPackVersion"] = "winoe-ai-pack-v4"
    monkeypatch.setattr(
        winoe_report_runner,
        "build_prompt_pack_entry",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("mutable prompt-pack lookup should not be used")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        winoe_report_runner,
        "resolve_winoe_report_aggregator_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("mutable runtime config lookup should not be used")
        ),
        raising=False,
    )
    (
        model_name,
        model_version,
        prompt_version,
        rubric_version,
        prompt_pack_version,
    ) = winoe_report_runner._resolve_winoe_report_run_identity(snapshot)

    assert model_name == "gpt-5.5"
    assert model_version == "gpt-5.5"
    assert prompt_version == "winoe-ai-pack-v4:winoeReport"
    assert rubric_version == "winoe-ai-pack-v4:winoeReport:rubric"
    assert prompt_pack_version == "winoe-ai-pack-v4"


def test_code_implementation_evidence_context_has_explicit_slots():
    bundle_field_names = {
        field.name for field in fields(evaluator.EvaluationInputBundle)
    }
    assert "code_implementation_evidence" in bundle_field_names

    evidence = evaluator.CodeImplementationEvidenceContext(
        repository_snapshot=None,
        repository_url="https://github.com/acme/repo",
        repository_reference="acme/repo",
        commit_history=[],
        file_creation_timeline=[],
        test_coverage_progression=[],
        evidence_status={
            "repository_snapshot": "unavailable: no day 2/3 repository or submission evidence found",
            "commit_history": "unavailable: evidence persistence not yet implemented",
            "file_creation_timeline": "unavailable: evidence persistence not yet implemented",
            "test_coverage_progression": "unavailable: evidence persistence not yet implemented",
        },
    )
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=1,
        scenario_version_id=2,
        model_name="model-x",
        model_version="v1",
        prompt_version="p1",
        rubric_version="r1",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=2, repo_full_name="acme/repo", commit_sha="abc")
        ],
        code_implementation_evidence=evidence,
        ai_policy_snapshot_json=_snapshot(),
    )

    assert bundle.code_implementation_evidence.repository_reference == "acme/repo"
    assert bundle.code_implementation_evidence.commit_history == []
    assert bundle.code_implementation_evidence.file_creation_timeline == []
    assert bundle.code_implementation_evidence.test_coverage_progression == []


def test_missing_code_implementation_evidence_is_explicit_in_prompt_context():
    evidence = evaluator.CodeImplementationEvidenceContext(
        repository_snapshot=None,
        repository_url="https://github.com/acme/repo",
        repository_reference="acme/repo",
        commit_history=[],
        file_creation_timeline=[],
        test_coverage_progression=[],
        evidence_status={
            "repository_snapshot": "unavailable: no day 2/3 repository or submission evidence found",
            "commit_history": "unavailable: complete commit history not yet persisted",
            "file_creation_timeline": "unavailable: file creation timeline artifacts not yet persisted",
            "test_coverage_progression": "unavailable: coverage progression artifacts not yet persisted",
        },
    )
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=1,
        scenario_version_id=2,
        model_name="model-x",
        model_version="v1",
        prompt_version="p1",
        rubric_version="r1",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=2, repo_full_name="acme/repo", commit_sha="abc")
        ],
        code_implementation_evidence=evidence,
        ai_policy_snapshot_json=_snapshot(),
    )

    run_context = evaluator_runtime._build_day_run_context(
        bundle,
        day_input(day_index=2, repo_full_name="acme/repo", commit_sha="abc"),
    )
    user_prompt = json.loads(
        evaluator_runtime._build_day_review_prompt(
            bundle=bundle,
            day_input=day_input(
                day_index=2, repo_full_name="acme/repo", commit_sha="abc"
            ),
            rubric_prompt="rubric guidance",
        )
    )

    assert "codeImplementationEvidence" in run_context
    assert "Do not infer process quality" in run_context
    assert "Repository snapshot status: unavailable:" in run_context
    assert (
        user_prompt["reviewContext"]["codeImplementationEvidence"][
            "repositoryReference"
        ]
        == "acme/repo"
    )
    assert (
        user_prompt["reviewContext"]["codeImplementationEvidence"]["commitHistory"]
        == []
    )
    assert user_prompt["reviewContext"]["instructions"].startswith(
        "Use codeImplementationEvidence as primary evidence"
    )


def test_populated_code_implementation_evidence_serializes_into_prompt_context():
    evidence = evaluator.CodeImplementationEvidenceContext(
        repository_snapshot={
            "candidateSessionId": 1,
            "repoFullName": "acme/repo",
            "repoUrl": "https://github.com/acme/repo",
        },
        repository_url="https://github.com/acme/repo",
        repository_reference="acme/repo",
        repository_artifact_references=[
            {
                "kind": "artifact_summary",
                "artifactName": "commitMetadata",
                "dayIndex": 2,
                "submissionId": 10,
                "artifactId": 11,
            }
        ],
        commit_history=[
            {
                "sha": "commit-sha-123",
                "message": "Add app scaffold",
                "committedAt": "2026-03-13T10:00:00Z",
                "authoredAt": "2026-03-13T10:00:00Z",
                "author": "codex",
                "filesChanged": 2,
                "filesChangedPaths": ["README.md", "src/app.py"],
                "additions": 120,
                "deletions": 14,
                "dayIndex": 2,
                "submissionId": 10,
                "evidenceArtifactId": 11,
            }
        ],
        file_creation_timeline=[
            {
                "path": "README.md",
                "createdAt": "2026-03-13T09:00:00Z",
                "firstCommitSha": "commit-sha-123",
                "commitMessage": "Bootstrap app",
                "dayIndex": 2,
                "submissionId": 10,
                "evidenceArtifactId": 12,
            }
        ],
        test_coverage_progression=[
            {
                "dayIndex": 2,
                "submissionId": 10,
                "commitSha": "commit-sha-123",
                "workflowRunId": "9001",
                "capturedAt": "2026-03-13T11:00:00Z",
                "testsPassed": 7,
                "testsFailed": 0,
                "coveragePath": "artifacts/coverage",
                "outputLog": "artifacts/test-results/test-output.log",
                "command": "python -m pytest",
                "detectedTool": "pytest",
                "exitCode": 0,
                "evidenceArtifactId": 15,
            }
        ],
        dependency_metadata={
            "dayIndex": 2,
            "submissionId": 10,
            "evidenceArtifactId": 13,
            "detected": True,
            "manifests": [{"path": "pyproject.toml", "kind": "python"}],
        },
        documentation_evolution=[
            {
                "dayIndex": 2,
                "submissionId": 10,
                "commitSha": "commit-sha-123",
                "message": "Add app scaffold",
                "documentationPaths": ["README.md"],
                "evidenceArtifactId": 11,
            }
        ],
        evidence_status={
            "repository_snapshot": "available: derived from day 2/3 repository and submission evidence",
            "commit_history": "available: derived from persisted submission.test_output summary evidenceArtifacts.commitMetadata",
            "file_creation_timeline": "available: derived from persisted submission.test_output summary evidenceArtifacts.fileCreationTimeline",
            "test_coverage_progression": "available: derived from persisted submission.test_output summary evidenceArtifacts.testResults and coveragePath",
            "dependency_metadata": "available: derived from persisted submission.test_output summary evidenceArtifacts.dependencyManifests",
            "documentation_evolution": "available: derived from commit history entries touching README or docs files",
        },
    )
    bundle = evaluator.EvaluationInputBundle(
        candidate_session_id=1,
        scenario_version_id=2,
        model_name="model-x",
        model_version="v1",
        prompt_version="p1",
        rubric_version="r1",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(day_index=2, repo_full_name="acme/repo", commit_sha="abc")
        ],
        code_implementation_evidence=evidence,
        ai_policy_snapshot_json=_snapshot(),
    )

    user_prompt = json.loads(
        evaluator_runtime._build_day_review_prompt(
            bundle=bundle,
            day_input=day_input(
                day_index=2, repo_full_name="acme/repo", commit_sha="abc"
            ),
            rubric_prompt="rubric guidance",
        )
    )

    serialized = user_prompt["reviewContext"]["codeImplementationEvidence"]
    assert serialized["commitHistory"]
    assert serialized["fileCreationTimeline"]
    assert serialized["testCoverageProgression"]
    assert serialized["evidenceStatus"]["commit_history"].startswith("available:")
    assert serialized["evidenceStatus"]["file_creation_timeline"].startswith(
        "available:"
    )
    assert serialized["evidenceStatus"]["test_coverage_progression"].startswith(
        "available:"
    )


def test_day_inputs_helpers_handle_malformed_evidence_payloads():
    submission = SimpleNamespace(
        id=41,
        test_output="",
        workflow_run_completed_at=None,
        last_run_at=None,
        tests_passed=None,
        tests_failed=None,
    )

    assert day_inputs_service._load_json_object("not json") is None
    assert day_inputs_service._load_json_object("[1, 2, 3]") is None
    assert (
        day_inputs_service._submission_test_summary(SimpleNamespace(test_output="   "))
        is None
    )
    assert day_inputs_service._submission_test_summary(
        SimpleNamespace(test_output='{"summary": 1}')
    ) == {"summary": 1}
    assert (
        day_inputs_service._summary_evidence_artifacts(
            SimpleNamespace(test_output='{"summary": {"evidenceArtifacts": []}}')
        )
        is None
    )
    assert (
        day_inputs_service._summary_without_evidence(
            SimpleNamespace(
                test_output='{"summary": {"evidenceArtifacts": {"commitMetadata": {}}}}'
            )
        )
        is None
    )
    assert day_inputs_service._load_json_object({}) == {}
    assert day_inputs_service._artifact_payload(None, "commitMetadata") == (None, None)
    assert day_inputs_service._artifact_payload(
        {"commitMetadata": "bad"}, "commitMetadata"
    ) == (None, None)
    assert day_inputs_service._artifact_payload(
        {"commitMetadata": {"data": []}}, "commitMetadata"
    ) == ({"data": []}, None)
    assert day_inputs_service._string_list([1, " README.md ", "", None]) == [
        "README.md"
    ]

    evidence_artifacts = {
        "commitMetadata": {
            "artifactId": 11,
            "data": {
                "payload": {
                    "commits": [
                        {"sha": "", "files_changed": ["README.md"]},
                        "bad-entry",
                        {
                            "sha": "commit-sha-abc",
                            "timestamp": "2026-03-13T10:00:00Z",
                            "message": "Add scaffold",
                            "files_changed": "README.md",
                            "files_changed_count": 5,
                        },
                    ]
                }
            },
        },
        "fileCreationTimeline": {
            "artifactId": 12,
            "data": {
                "payload": {
                    "files": [
                        {"timestamp": "2026-03-13T09:00:00Z", "files": "README.md"},
                        {
                            "timestamp": "2026-03-13T09:30:00Z",
                            "commit_sha": "commit-sha-abc",
                            "message": "Bootstrap app",
                            "files": ["README.md", "", "src/app.py"],
                        },
                    ]
                }
            },
        },
        "dependencyManifests": {
            "artifactId": 13,
            "data": {"payload": {"detected": True, "manifests": "invalid"}},
        },
        "testResults": {
            "artifactId": 14,
            "data": {
                "payload": {
                    "summary": {"outputLog": "artifacts/test-results/test-output.log"}
                }
            },
        },
    }

    commit_history = day_inputs_service._commit_history_from_submission(
        submission=submission,
        day_index=2,
        evidence_artifacts=evidence_artifacts,
    )
    assert len(commit_history) == 1
    assert commit_history[0]["sha"] == "commit-sha-abc"
    assert commit_history[0]["filesChanged"] == 5
    assert commit_history[0]["filesChangedPaths"] == []

    file_creation_timeline = day_inputs_service._file_creation_timeline_from_submission(
        submission=submission,
        day_index=2,
        evidence_artifacts=evidence_artifacts,
    )
    assert len(file_creation_timeline) == 2
    assert file_creation_timeline[0]["path"] == "README.md"
    assert file_creation_timeline[1]["path"] == "src/app.py"

    assert (
        day_inputs_service._dependency_metadata_from_submission(
            day_index=2,
            submission=submission,
            evidence_artifacts=evidence_artifacts,
        )
        is None
    )
    assert (
        day_inputs_service._commit_history_from_submission(
            submission=submission,
            day_index=2,
            evidence_artifacts=None,
        )
        == []
    )
    assert (
        day_inputs_service._commit_history_from_submission(
            submission=submission,
            day_index=2,
            evidence_artifacts={
                "commitMetadata": {"data": {"payload": {"commits": {}}}}
            },
        )
        == []
    )
    assert (
        day_inputs_service._file_creation_timeline_from_submission(
            submission=submission,
            day_index=2,
            evidence_artifacts=None,
        )
        == []
    )
    assert (
        day_inputs_service._file_creation_timeline_from_submission(
            submission=submission,
            day_index=2,
            evidence_artifacts={
                "fileCreationTimeline": {"data": {"payload": {"files": {}}}}
            },
        )
        == []
    )
    assert (
        day_inputs_service._repository_snapshot_status(
            repository_reference=None,
            day_submission_refs=[{"dayIndex": 2}],
            commit_history=[],
            file_creation_timeline=[],
            test_coverage_progression=[],
            dependency_metadata=None,
            documentation_evolution=[],
        )
        == "partial: day 2/3 submission evidence available; repository reference not resolved and persisted repository snapshot artifacts not found"
    )
    assert (
        day_inputs_service._test_coverage_progression_from_submission(
            day_index=2,
            submission=submission,
            evidence_artifacts=None,
        )
        == []
    )
    assert (
        day_inputs_service._test_coverage_progression_from_submission(
            day_index=2,
            submission=submission,
            evidence_artifacts=evidence_artifacts,
        )
        == []
    )
    assert (
        day_inputs_service._documentation_evolution_from_commit_history(
            [{"filesChangedPaths": "README.md"}]
        )
        == []
    )

    documentation = day_inputs_service._documentation_evolution_from_commit_history(
        [
            {
                "dayIndex": 2,
                "submissionId": 41,
                "sha": "commit-sha-abc",
                "message": "Docs update",
                "filesChangedPaths": ["README.md", "docs/guide.md", "src/app.py"],
            }
        ]
    )
    assert documentation[0]["documentationPaths"] == [
        "README.md",
        "docs/guide.md",
    ]


def test_repository_snapshot_status_distinguishes_repo_reference_from_full_evidence():
    assert (
        day_inputs_service._repository_snapshot_status(
            repository_reference="acme/repo",
            day_submission_refs=[{"dayIndex": 2}],
            commit_history=[],
            file_creation_timeline=[],
            test_coverage_progression=[],
            dependency_metadata=None,
            documentation_evolution=[],
        )
        == "partial: repository reference available; persisted repository snapshot artifacts not found for day 2/3 evidence"
    )
    assert (
        day_inputs_service._repository_snapshot_status(
            repository_reference=None,
            day_submission_refs=[],
            commit_history=[],
            file_creation_timeline=[],
            test_coverage_progression=[],
            dependency_metadata=None,
            documentation_evolution=[],
        )
        == "unavailable: no day 2/3 repository or submission evidence found"
    )
