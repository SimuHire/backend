from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.evaluations.repositories.evaluations_repositories_evaluations_reviewer_report_model import (
    EvaluationReviewerReport,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_run_model import (
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_trial_agent_snapshot_model import (
    TrialAgentSnapshot,
)
from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationState,
    TrialEvaluationStateRecord,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_jobs_service import (
    EVALUATION_RUN_JOB_TYPE,
)
from app.evaluations.services.evaluations_services_trial_evaluator_service import (
    REVIEWER_AGENT_KEYS,
    TrialEvaluator,
    get_trial_evaluation_state,
)
from app.media.repositories.recordings.media_repositories_recordings_media_recordings_core_model import (
    RECORDING_ASSET_STATUS_READY,
    RecordingAsset,
)
from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    TRANSCRIPT_STATUS_READY,
    Transcript,
)
from app.notifications.repositories.notifications_repositories_notifications_delivery_audits_core_model import (
    NotificationDeliveryAudit,
)
from app.notifications.services.notifications_services_notifications_talent_partner_updates_service import (
    WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
)
from app.shared.database.shared_database_models_model import Job, WinoeReport
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_SUCCEEDED,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_citation_model import (
    WinoeReportCitation,
)
from tests.evaluations.services.evaluations_winoe_report_fixtures_utils import (
    build_valid_winoe_report_json,
)
from tests.shared.factories import (
    create_candidate_session,
    create_submission,
    create_talent_partner,
    create_trial,
)


@pytest.mark.asyncio
async def test_completed_day_5_dispatches_canonical_evaluation_job(async_session):
    trial, tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    await async_session.commit()

    result = await TrialEvaluator(async_session).evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert result.state == TrialEvaluationState.REVIEWERS_DISPATCHED
    evaluation_jobs = (
        (
            await async_session.execute(
                Job.__table__.select().where(
                    Job.job_type == EVALUATION_RUN_JOB_TYPE,
                    Job.candidate_session_id == candidate_session.id,
                )
            )
        )
        .mappings()
        .all()
    )
    reviewer_jobs = await async_session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.job_type == "evaluation_reviewer",
            Job.candidate_session_id == candidate_session.id,
        )
    )
    assert len(evaluation_jobs) == 1
    assert reviewer_jobs == 0
    assert evaluation_jobs[0]["payload_json"]["candidateSessionId"] == (
        candidate_session.id
    )
    assert result.correlation_id == evaluation_jobs[0]["correlation_id"]


@pytest.mark.asyncio
async def test_evaluation_does_not_start_when_required_artifacts_missing(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="trial-evaluator-missing@test.com"
    )
    trial, tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
    )
    await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[0],
        content_text="Day 1",
    )
    await async_session.commit()

    result = await TrialEvaluator(async_session).evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert result.state == TrialEvaluationState.DAY_5_DEADLINE_PASSED
    assert "day_5_submission" in result.missing_artifacts
    assert "day_4_demo_transcript_ready" not in result.missing_artifacts
    reviewer_job_count = await async_session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.job_type == EVALUATION_RUN_JOB_TYPE)
    )
    assert reviewer_job_count == 0


@pytest.mark.asyncio
async def test_incomplete_candidate_session_stays_awaiting_deadline(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="trial-evaluator-awaiting@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="in_progress",
        completed_at=None,
    )
    await async_session.commit()

    result = await TrialEvaluator(async_session).evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert result.state == TrialEvaluationState.AWAITING_DAY_5_DEADLINE
    assert result.failure_context == {"reason": "candidate_session_not_completed"}


@pytest.mark.asyncio
async def test_reviewers_complete_without_report_queues_winoe_synthesis(
    async_session,
):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    await _seed_reviewer_reports(async_session, candidate_session)
    await async_session.commit()

    result = await TrialEvaluator(async_session).evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert result.state == TrialEvaluationState.WINOE_SYNTHESIZING
    assert result.failure_context is not None
    assert result.failure_context["reason"] == "winoe_report_missing"
    assert result.jobs
    job = await async_session.get(Job, result.jobs[0])
    assert job is not None
    assert job.job_type == EVALUATION_RUN_JOB_TYPE


@pytest.mark.asyncio
async def test_successful_pipeline_reaches_notification_state(async_session):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    run = await _seed_reviewer_reports(async_session, candidate_session)
    report = WinoeReport(
        candidate_session_id=candidate_session.id,
        generated_at=datetime.now(UTC),
    )
    async_session.add(report)
    await async_session.flush()
    for citation in build_valid_winoe_report_json()["citations"]:
        async_session.add(
            WinoeReportCitation(
                report_id=report.id,
                dimension=str(citation["dimension"]),
                artifact_type=str(citation["artifact_type"]),
                artifact_ref=str(citation["artifact_ref"]),
                excerpt=str(citation["excerpt"]),
            )
        )
    async_session.add(
        NotificationDeliveryAudit(
            notification_type=WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
            candidate_session_id=candidate_session.id,
            trial_id=trial.id,
            recipient_email="tp-evaluator@test.com",
            recipient_role="talent_partner",
            subject="Jordan's Winoe Report is ready",
            status="sent",
            provider="test",
            idempotency_key="report-ready",
            attempted_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
        )
    )
    await async_session.commit()

    result = await TrialEvaluator(async_session).evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert run.id is not None
    assert result.state == TrialEvaluationState.NOTIFICATION_SENT
    assert all(item["complete"] for item in result.reviewer_status.values())


@pytest.mark.asyncio
async def test_fresh_seeded_submission_fast_forwards_through_terminal_states(
    async_session, monkeypatch
):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    await async_session.commit()
    evaluator = TrialEvaluator(async_session)
    transition_log: list[str] = []
    original_transition = evaluator._transition

    async def _recording_transition(*args, **kwargs):
        state = args[1]
        transition_log.append(state.value)
        return await original_transition(*args, **kwargs)

    monkeypatch.setattr(evaluator, "_transition", _recording_transition)

    first = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )
    assert first.state == TrialEvaluationState.REVIEWERS_DISPATCHED

    await _seed_reviewer_reports(async_session, candidate_session)
    second = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert second.state == TrialEvaluationState.WINOE_SYNTHESIZING

    report = WinoeReport(
        candidate_session_id=candidate_session.id,
        generated_at=datetime.now(UTC),
    )
    async_session.add(report)
    await async_session.flush()
    for citation in build_valid_winoe_report_json()["citations"]:
        async_session.add(
            WinoeReportCitation(
                report_id=report.id,
                dimension=str(citation["dimension"]),
                artifact_type=str(citation["artifact_type"]),
                artifact_ref=str(citation["artifact_ref"]),
                excerpt=str(citation["excerpt"]),
            )
        )
    async_session.add(
        NotificationDeliveryAudit(
            notification_type=WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
            candidate_session_id=candidate_session.id,
            trial_id=trial.id,
            recipient_email="tp-evaluator@test.com",
            recipient_role="talent_partner",
            subject="Jordan's Winoe Report is ready",
            status="sent",
            provider="test",
            idempotency_key="report-ready-fast-forward",
            attempted_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
        )
    )
    await async_session.commit()

    third = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert third.state == TrialEvaluationState.NOTIFICATION_SENT
    ordered_states = [
        TrialEvaluationState.REVIEWERS_DISPATCHED.value,
        TrialEvaluationState.REVIEWERS_COMPLETE.value,
        TrialEvaluationState.WINOE_SYNTHESIZING.value,
        TrialEvaluationState.EVIDENCE_TRAIL_VALIDATING.value,
        TrialEvaluationState.REPORT_FINALIZED.value,
        TrialEvaluationState.NOTIFICATION_SENT.value,
    ]
    index = -1
    for state in ordered_states:
        next_index = transition_log.index(state)
        assert next_index > index
        index = next_index


@pytest.mark.asyncio
async def test_reviewers_complete_waits_for_all_required_reviewers(async_session):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    await _seed_reviewer_reports(
        async_session,
        candidate_session,
        reviewer_keys=REVIEWER_AGENT_KEYS[:-1],
    )
    await async_session.commit()

    result = await TrialEvaluator(async_session).evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert result.state == TrialEvaluationState.REVIEWERS_DISPATCHED
    assert result.reviewer_status["reflectionEssayReviewer"]["complete"] is False
    assert len(result.jobs) == 1
    job = await async_session.get(Job, result.jobs[0])
    assert job is not None
    assert job.job_type == EVALUATION_RUN_JOB_TYPE


@pytest.mark.asyncio
async def test_validation_failure_retries_synthesis_then_marks_failed(async_session):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    await _seed_reviewer_reports(
        async_session,
        candidate_session,
        raw_report_json={
            "dimensions": [
                {
                    "name": "Communication",
                    "score": 8,
                    "justification": "Demo claim without citation.",
                }
            ],
            "citations": [],
        },
    )
    async_session.add(
        WinoeReport(
            candidate_session_id=candidate_session.id,
            generated_at=datetime.now(UTC),
        )
    )
    await async_session.commit()

    evaluator = TrialEvaluator(async_session)
    first = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )
    second = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )
    final = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert first.state == TrialEvaluationState.WINOE_SYNTHESIZING
    assert first.failure_context is not None
    assert first.failure_context["validationRetryCount"] == 1
    assert second.state == TrialEvaluationState.WINOE_SYNTHESIZING
    assert second.failure_context is not None
    assert second.failure_context["validationRetryCount"] == 2
    assert final.state == TrialEvaluationState.FAILED
    assert final.failure_context is not None
    assert final.failure_context["errorCode"] == "evidence_trail_validation_failed"
    assert "missing persisted Evidence Trail citations" in " ".join(
        final.failure_context["errors"]
    )


@pytest.mark.asyncio
async def test_evaluator_exception_marks_state_failed(async_session, monkeypatch):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    await async_session.commit()
    evaluator = TrialEvaluator(async_session)

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("forced evaluator failure")

    monkeypatch.setattr(evaluator, "_load_trial_and_session", _raise)

    result = await evaluator.evaluate(
        trial_id=trial.id,
        candidate_session_id=candidate_session.id,
    )

    assert result.state == TrialEvaluationState.FAILED
    assert result.failure_context == {
        "errorType": "RuntimeError",
        "message": "forced evaluator failure",
    }


@pytest.mark.asyncio
async def test_persisted_evidence_validator_reports_broken_citations(
    async_session,
):
    _trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    run = await _seed_reviewer_reports(
        async_session,
        candidate_session,
        raw_report_json={
            "dimensions": [
                {},
                {"name": "Architecture", "score": True},
                {"name": "Uncited", "score": 0.7},
            ],
            "dayScores": [{"dayIndex": 4, "score": 0.8}],
            "citations": [{"dimension": "raw-only"}],
        },
    )
    report = WinoeReport(
        candidate_session_id=candidate_session.id,
        generated_at=datetime.now(UTC),
    )
    async_session.add(report)
    await async_session.flush()
    async_session.add_all(
        [
            WinoeReportCitation(
                report_id=report.id,
                dimension="",
                artifact_type="submission",
                artifact_ref="submission:1",
                excerpt="candidate evidence",
            ),
            WinoeReportCitation(
                report_id=report.id,
                dimension="Architecture",
                artifact_type="",
                artifact_ref="bad locator",
                excerpt="",
            ),
            WinoeReportCitation(
                report_id=report.id,
                dimension="BriefOnly",
                artifact_type="project_brief",
                artifact_ref="submission:1",
                excerpt="brief text",
            ),
        ]
    )
    await async_session.flush()

    result = await TrialEvaluator(async_session)._validate_persisted_report(
        run=run,
        report=report,
        reviewer_status={key: {"complete": True} for key in REVIEWER_AGENT_KEYS},
    )

    errors = " ".join(result.errors)
    assert result.passed is False
    assert "Citation is missing dimension" in errors
    assert "missing artifact_type" in errors
    assert "unsupported locator" in errors
    assert "missing excerpt" in errors
    assert "points only to the Project Brief" in errors
    assert "Scored dimension is missing name" in errors
    assert "missing a numeric score" in errors
    assert "missing Evidence Trail citation" in errors
    assert "Day 4 communication or demo claims require a transcript citation" in errors
    assert result.metadata["rawReportCitationCount"] == 1


@pytest.mark.asyncio
async def test_persisted_evidence_validator_reports_missing_core_fields(
    async_session,
):
    _trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    run = await _seed_reviewer_reports(
        async_session,
        candidate_session,
        raw_report_json={},
    )
    run.raw_report_json = {}
    report = WinoeReport(
        candidate_session_id=candidate_session.id,
        generated_at=datetime.now(UTC),
    )
    async_session.add(report)
    await async_session.flush()
    async_session.add(
        WinoeReportCitation(
            report_id=report.id,
            dimension="Architecture",
            artifact_type="submission",
            artifact_ref="",
            excerpt="candidate evidence",
        )
    )
    await async_session.flush()

    result = await TrialEvaluator(async_session)._validate_persisted_report(
        run=run,
        report=report,
        reviewer_status={
            key: {"complete": key != "reflectionEssayReviewer"}
            for key in REVIEWER_AGENT_KEYS
        },
    )

    errors = " ".join(result.errors)
    assert result.passed is False
    assert "missing raw Winoe Report JSON" in errors
    assert "Missing reviewer report: reflectionEssayReviewer" in errors
    assert "missing scored dimensions" in errors
    assert "missing artifact_ref" in errors


@pytest.mark.asyncio
async def test_persisted_evidence_validator_rejects_project_brief_only_evidence(
    async_session,
):
    _trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    run = await _seed_reviewer_reports(
        async_session,
        candidate_session,
        raw_report_json={
            "dimensions": [{"name": "Architecture", "score": 0.7}],
            "citations": [],
        },
    )
    report = WinoeReport(
        candidate_session_id=candidate_session.id,
        generated_at=datetime.now(UTC),
    )
    async_session.add(report)
    await async_session.flush()
    async_session.add(
        WinoeReportCitation(
            report_id=report.id,
            dimension="Architecture",
            artifact_type="project_brief",
            artifact_ref="submission:1",
            excerpt="brief text",
        )
    )
    await async_session.flush()

    result = await TrialEvaluator(async_session)._validate_persisted_report(
        run=run,
        report=report,
        reviewer_status={key: {"complete": True} for key in REVIEWER_AGENT_KEYS},
    )

    assert result.passed is False
    assert "do not point to candidate artifacts" in " ".join(result.errors)


@pytest.mark.asyncio
async def test_notification_sent_check_accepts_successful_job(async_session):
    trial, _tasks, candidate_session = await _completed_trial_with_submissions(
        async_session
    )
    async_session.add(
        Job(
            job_type=WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
            status=JOB_STATUS_SUCCEEDED,
            idempotency_key=f"report-ready:{candidate_session.id}",
            payload_json={"candidateSessionId": candidate_session.id},
            company_id=trial.company_id,
            candidate_session_id=candidate_session.id,
        )
    )
    await async_session.commit()

    sent = await TrialEvaluator(async_session)._report_ready_notification_sent(
        candidate_session_id=candidate_session.id,
    )

    assert sent is True


@pytest.mark.asyncio
async def test_agent_versions_and_state_listing(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="trial-evaluator-state@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(async_session, trial=trial)
    async_session.add_all(
        [
            TrialAgentSnapshot(
                trial_id=trial.id,
                agent_name="Unknown Reviewer",
                agent_type="reviewer",
                model_provider="test",
                model_name="ignored",
                model_version="v1",
                prompt_version="p1",
                prompt_content="prompt",
                prompt_content_hash="c" * 64,
                rubric_version="r1",
                rubric_content="rubric",
                rubric_content_hash="d" * 64,
            ),
            TrialEvaluationStateRecord(
                trial_id=trial.id,
                candidate_session_id=candidate_session.id,
                state=TrialEvaluationState.REPORT_FINALIZED.value,
                correlation_id="trial-state",
                reviewer_status_json={"designDocReviewer": {"complete": True}},
                winoe_synthesis_status="complete",
                evidence_trail_validation_status="passed",
                report_finalization_status="finalized",
                notification_status="queued_or_pending",
                failure_context_json={"validation": {"passed": True}},
            ),
        ]
    )
    await async_session.commit()

    versions = await TrialEvaluator(async_session)._agent_versions(trial_id=trial.id)
    state = await get_trial_evaluation_state(async_session, trial_id=trial.id)

    assert "designDocReviewer" in versions
    assert "ignored" not in versions.values()
    assert state["trialId"] == trial.id
    assert state["candidateSessions"][0]["candidateSessionId"] == candidate_session.id
    assert state["candidateSessions"][0]["reportFinalizationStatus"] == "finalized"


def test_trial_evaluator_static_validation_helpers():
    assert (
        TrialEvaluator._requires_day4_transcript_citation(
            {
                "dimensions": [
                    "ignored",
                    {"name": "Architecture", "score": 0},
                    {"name": "Delivery", "justification": "Clear handoff narrative"},
                ]
            }
        )
        is True
    )
    assert (
        TrialEvaluator._requires_day4_transcript_citation(
            {"dayScores": ["ignored", {"dayIndex": 4, "score": 0.5}]}
        )
        is True
    )
    assert (
        TrialEvaluator._requires_day4_transcript_citation(
            {"dimensions": [{"name": "Architecture", "score": 0}]}
        )
        is False
    )
    assert TrialEvaluator._clean_text(42) == ""
    record = TrialEvaluationStateRecord(
        trial_id=1,
        candidate_session_id=1,
        state=TrialEvaluationState.FAILED.value,
        correlation_id="test",
        failure_context_json=["not-a-dict"],
    )
    assert TrialEvaluator._validation_retry_count(record) == 0


async def _completed_trial_with_submissions(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="trial-evaluator@test.com"
    )
    trial, tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Jordan Candidate",
        invite_email="candidate-evaluator@test.com",
        candidate_email="candidate-evaluator@test.com",
        status="completed",
        completed_at=datetime.now(UTC),
    )
    for task in tasks:
        recording_id = None
        if task.day_index == 4:
            recording = RecordingAsset(
                candidate_session_id=candidate_session.id,
                task_id=task.id,
                storage_key=f"recordings/{candidate_session.id}/{task.id}.webm",
                content_type="video/webm",
                bytes=1024,
                status=RECORDING_ASSET_STATUS_READY,
            )
            async_session.add(recording)
            await async_session.flush()
            async_session.add(
                Transcript(
                    recording_id=recording.id,
                    text="Demo transcript",
                    status=TRANSCRIPT_STATUS_READY,
                )
            )
            await async_session.flush()
            recording_id = recording.id
        await create_submission(
            async_session,
            candidate_session=candidate_session,
            task=task,
            content_text=f"Day {task.day_index}",
            recording_id=recording_id,
        )
    return trial, tasks, candidate_session


async def _seed_reviewer_reports(
    async_session,
    candidate_session,
    *,
    reviewer_keys=REVIEWER_AGENT_KEYS,
    raw_report_json=None,
):
    run = EvaluationRun(
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status="completed",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        model_name="test",
        model_version="test",
        prompt_version="test",
        rubric_version="test",
        basis_fingerprint="fingerprint",
        overall_winoe_score=0.8,
        recommendation=None,
        confidence=0.8,
        generated_at=datetime.now(UTC),
        raw_report_json=raw_report_json or build_valid_winoe_report_json(),
        metadata_json={},
        day2_checkpoint_sha="sha2",
        day3_final_sha="sha3",
        cutoff_commit_sha="sha5",
        transcript_reference="transcript:1",
    )
    async_session.add(run)
    await async_session.flush()
    for index, reviewer_key in enumerate(reviewer_keys, start=1):
        async_session.add(
            EvaluationReviewerReport(
                run_id=run.id,
                reviewer_agent_key=reviewer_key,
                day_index=index if index < 4 else 5 if index == 4 else index,
                submission_kind="text",
                score=0.8,
                dimensional_scores_json={"signal": 0.8},
                evidence_citations_json=[],
                assessment_text="Evidence-backed Trial review.",
                strengths_json=["Clear evidence"],
                risks_json=[],
                raw_output_json={},
            )
        )
    await async_session.flush()
    return run
