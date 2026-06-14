from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.candidates.candidate_sessions.repositories.candidates_candidate_sessions_repositories_candidates_candidate_sessions_day_audit_model import (
    CandidateDayAudit,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EvaluationDayScore,
    EvaluationReviewerReport,
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_create_run_with_scores_repository import (
    create_run_with_day_scores,
)
from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationStateRecord,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_api_service import (
    fetch_winoe_report,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_citations_service import (
    get_report_citations,
)
from app.integrations.github import FakeGithubClient, GithubActionsRunner
from app.media.repositories.recordings.media_repositories_recordings_media_recordings_core_model import (
    RecordingAsset,
)
from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    Transcript,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Company,
    ScenarioVersion,
    Submission,
    Task,
    TaskDraft,
    Trial,
    User,
    WinoeReport,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_core_model import (
    Workspace,
    WorkspaceGroup,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_citation_model import (
    WinoeReportCitation,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_repository import (
    upsert_marker,
)
from app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_codespace_status_service import (
    codespace_status,
)
from app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_run_tests_service import (
    run_task_tests,
)
from scripts import seed_demo as seed_demo_script
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)


class _SharedSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _SharedSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SharedSessionContext(self._session)


def _session_maker(async_session):
    return _SharedSessionMaker(async_session)


def _seed_args(
    *,
    reset_db: bool = False,
    talent_partner_email: str = "winoetalentpartner@gmail.com",
    talent_partner_name: str = "TalentPartner",
    company_name: str = "Northstar Labs",
    qa_candidate_email: str = "winoecandidate@gmail.com",
    github_provider: str = "fake",
    allow_production_write: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        reset_db=reset_db,
        talent_partner_email=talent_partner_email,
        talent_partner_name=talent_partner_name,
        company_name=company_name,
        qa_candidate_email=qa_candidate_email,
        github_provider=github_provider,
        allow_production_write=allow_production_write,
    )


def _assert_no_retired_terms(text: str) -> None:
    denylist = [
        "te" "non",
        "si" "muhire",
        "re" "cruiter",
        "simu" "lation",
        "fit " "profile",
        "fit_" "profile",
        "fit " "score",
        "fit_" "score",
        "tem" + "plate",
        "tem" + "plate" + "_catalog",
        "pre" + "commit",
        "spe" + "cializor",
        "codespace " + "specification",
        "codespace" + "_spec",
        "starter " + "code",
        "pre-populated " + "codebase",
    ]
    lowered = text.lower()
    for term in denylist:
        assert term not in lowered


def _line_slice(text: str, start_line: int, end_line: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[start_line - 1 : end_line])


async def _assert_evidence_links(
    *,
    reviewer_reports: list[dict[str, object]],
) -> None:
    for reviewer_report in reviewer_reports:
        evidence_citations = reviewer_report.get("evidenceCitations") or []
        assert evidence_citations
        for citation in evidence_citations:
            assert isinstance(citation, dict)
            kind = citation.get("kind")
            ref = citation.get("ref")
            dimension_key = citation.get("dimensionKey")
            dimension_label = citation.get("dimensionLabel")
            assert isinstance(kind, str) and kind
            assert isinstance(ref, str) and ref
            assert isinstance(dimension_key, str) and dimension_key
            assert isinstance(dimension_label, str) and dimension_label
            if kind in {"commit", "diff", "commit_range"}:
                sha_prefix = ref.split(":", 1)[0]
                assert len(sha_prefix) == 40
                continue
            if kind in {"rubric", "submission"}:
                assert re.search(r":L\d+(?:-L?\d+)?$", ref)
                continue
            if kind == "tests":
                assert ref == "day2-tests.txt:L1-L4"
                continue
            if kind == "transcript":
                assert ref == "[00:00-02:00]"
                continue
            raise AssertionError(f"unexpected evidence citation kind: {kind}")


@pytest.mark.asyncio
async def test_seed_demo_cli_creates_complete_dataset_and_is_idempotent(
    async_session, monkeypatch, capsys
):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    args = _seed_args()
    await seed_demo_script._main_async(args)
    async_session.expire_all()
    await seed_demo_script._main_async(args)

    output = capsys.readouterr().out
    assert "demo-scoped refresh only" in output
    assert "using GitHub provider=fake" in output
    assert "using AI runtime=demo" in output

    company_count = await async_session.scalar(
        select(func.count()).select_from(Company)
    )
    user_count = await async_session.scalar(select(func.count()).select_from(User))
    trial_count = await async_session.scalar(select(func.count()).select_from(Trial))
    candidate_session_count = await async_session.scalar(
        select(func.count()).select_from(CandidateSession)
    )
    submission_count = await async_session.scalar(
        select(func.count()).select_from(Submission)
    )
    report_count = await async_session.scalar(
        select(func.count()).select_from(WinoeReport)
    )
    citation_count = await async_session.scalar(
        select(func.count()).select_from(WinoeReportCitation)
    )
    run_count = await async_session.scalar(
        select(func.count()).select_from(EvaluationRun)
    )
    day_score_count = await async_session.scalar(
        select(func.count()).select_from(EvaluationDayScore)
    )
    reviewer_count = await async_session.scalar(
        select(func.count()).select_from(EvaluationReviewerReport)
    )
    evaluation_state_count = await async_session.scalar(
        select(func.count()).select_from(TrialEvaluationStateRecord)
    )
    workspace_count = await async_session.scalar(
        select(func.count()).select_from(Workspace)
    )
    workspace_group_count = await async_session.scalar(
        select(func.count()).select_from(WorkspaceGroup)
    )
    recording_count = await async_session.scalar(
        select(func.count()).select_from(RecordingAsset)
    )
    transcript_count = await async_session.scalar(
        select(func.count()).select_from(Transcript)
    )
    audit_count = await async_session.scalar(
        select(func.count()).select_from(CandidateDayAudit)
    )
    scenario_version_count = await async_session.scalar(
        select(func.count()).select_from(ScenarioVersion)
    )
    task_count = await async_session.scalar(select(func.count()).select_from(Task))

    assert company_count == 1
    assert user_count == 2
    assert trial_count == 3
    assert candidate_session_count == 3
    assert submission_count == 6
    assert report_count == 1
    assert run_count == 1
    assert day_score_count == 5
    assert reviewer_count == 5
    assert evaluation_state_count == 1
    assert workspace_count == 2
    assert workspace_group_count == 2
    assert recording_count == 1
    assert transcript_count == 1
    assert audit_count == 2
    assert citation_count and citation_count > 0
    assert scenario_version_count == 3
    assert task_count == 15

    talent_partner = await async_session.scalar(
        select(User).where(User.email == "winoetalentpartner@gmail.com")
    )
    assert talent_partner is not None
    candidate_user = await async_session.scalar(
        select(User).where(User.email == "winoecandidate@gmail.com")
    )
    assert candidate_user is not None
    assert candidate_user.role == "candidate"
    assert candidate_user.company_id is None

    trial = await async_session.scalar(
        select(Trial).where(Trial.title == "Senior Frontend Engineer Trial")
    )
    assert trial is not None
    assert trial.scenario_template == ""
    assert trial.status == "completed"
    assert "from-scratch product surface" in trial.focus
    assert trial.company_context == {
        "companyName": "Northstar Labs",
        "preferredLanguageFramework": "TypeScript + React",
        "demoMode": "yc-demo",
    }
    assert isinstance(trial.company_rubric_json, dict)
    assert set(trial.company_rubric_json).issuperset(
        {
            "designDocReviewer",
            "codeImplementationReviewer",
            "demoPresentationReviewer",
            "reflectionEssayReviewer",
            "winoeReport",
        }
    )
    assert all(
        isinstance(trial.company_rubric_json[key], dict)
        for key in (
            "designDocReviewer",
            "codeImplementationReviewer",
            "demoPresentationReviewer",
            "reflectionEssayReviewer",
            "winoeReport",
        )
    )

    brief_text = await async_session.scalar(
        select(ScenarioVersion.project_brief_md).where(
            ScenarioVersion.trial_id == trial.id
        )
    )
    assert brief_text is not None
    assert "Project Brief" in brief_text
    assert "from-scratch work Trial" in brief_text
    _assert_no_retired_terms(str(brief_text))

    candidate_sessions = (
        (
            await async_session.execute(
                select(CandidateSession).order_by(CandidateSession.id)
            )
        )
        .scalars()
        .all()
    )
    assert [row.candidate_name for row in candidate_sessions] == [
        "Sarah Chen",
        "Nina Alvarez",
        "Priya Patel",
    ]
    assert [row.status for row in candidate_sessions] == [
        "completed",
        "in_progress",
        "not_started",
    ]
    assert [row.completed_at is not None for row in candidate_sessions] == [
        True,
        False,
        False,
    ]
    assert [len(row.day_windows_json or []) for row in candidate_sessions] == [
        5,
        5,
        0,
    ]
    awaiting_trial = await async_session.scalar(
        select(Trial).where(Trial.id == candidate_sessions[2].trial_id)
    )
    assert awaiting_trial is not None
    assert awaiting_trial.status == "active_inviting"
    assert candidate_sessions[1].invite_email == "winoecandidate@gmail.com"
    assert candidate_sessions[1].candidate_auth0_email == "winoecandidate@gmail.com"
    assert candidate_sessions[1].completed_at is None
    assert [day["status"] for day in candidate_sessions[0].day_windows_json or []] == [
        "submitted",
        "submitted",
        "submitted",
        "submitted",
        "submitted",
    ]
    assert [day["status"] for day in candidate_sessions[1].day_windows_json or []] == [
        "submitted",
        "in_progress",
        "locked",
        "locked",
        "locked",
    ]
    active_trial = await async_session.scalar(
        select(Trial).where(Trial.id == candidate_sessions[1].trial_id)
    )
    assert active_trial is not None
    assert active_trial.status == "active_inviting"
    assert candidate_sessions[1].candidate_user_id == candidate_user.id
    assert candidate_sessions[1].candidate_email == "winoecandidate@gmail.com"
    assert candidate_sessions[1].status == "in_progress"
    assert candidate_sessions[1].started_at is not None

    submission_rows = (
        await async_session.execute(
            select(Submission, Task.day_index)
            .join(Task, Submission.task_id == Task.id)
            .order_by(Submission.candidate_session_id, Task.day_index)
        )
    ).all()
    assert len(submission_rows) == 6
    expected_artifacts = {
        1: "design_document",
        2: "implementation_kickoff",
        3: "implementation_wrap_up",
        4: "handoff_transcript",
        5: "reflection_essay",
    }
    per_candidate_day_indexes: dict[int, list[int]] = {}
    for submission, day_index in submission_rows:
        per_candidate_day_indexes.setdefault(
            submission.candidate_session_id, []
        ).append(day_index)
        assert submission.content_json["artifactType"] == expected_artifacts[day_index]
        if day_index == 4:
            assert submission.recording_id is not None
            assert (
                submission.content_json["transcriptRecordingId"]
                == submission.recording_id
            )
    assert [1, 2, 3, 4, 5] in per_candidate_day_indexes.values()
    assert [1] in per_candidate_day_indexes.values()

    recording_rows = (
        (
            await async_session.execute(
                select(RecordingAsset).order_by(RecordingAsset.candidate_session_id)
            )
        )
        .scalars()
        .all()
    )
    transcript_rows = (
        (
            await async_session.execute(
                select(Transcript).order_by(Transcript.recording_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(recording_rows) == 1
    assert len(transcript_rows) == 1

    reports = (
        (await async_session.execute(select(WinoeReport).order_by(WinoeReport.id)))
        .scalars()
        .all()
    )
    assert len(reports) == 1
    evaluation_state = await async_session.scalar(
        select(TrialEvaluationStateRecord).where(
            TrialEvaluationStateRecord.candidate_session_id == candidate_sessions[0].id
        )
    )
    assert evaluation_state is not None
    assert evaluation_state.state == "notification_sent"
    assert evaluation_state.evidence_trail_validation_status == "passed"
    assert evaluation_state.report_finalization_status == "finalized"

    first_report = await fetch_winoe_report(
        async_session,
        candidate_session_id=candidate_sessions[0].id,
        user=talent_partner,
    )

    assert first_report["status"] == "ready"
    report = first_report["report"]
    assert isinstance(report["overallWinoeScore"], float)
    assert len(report["dayScores"]) == 5
    assert len(report["reviewerReports"]) == 5
    assert len(report["dimensions"]) == 8
    assert len(report["citations"]) == 15
    assert report["verdictOneLiner"]
    assert report["narrativeAssessment"]
    assert report["cohortContext"]
    assert [dimension["name"] for dimension in report["dimensions"]] == [
        "Architecture & Design",
        "Problem Understanding",
        "Implementation Quality",
        "Code Quality",
        "Testing Discipline",
        "Development Process",
        "Communication",
        "Reflection & Ownership",
    ]
    assert {citation["dimension"] for citation in report["citations"]} == {
        "Architecture & Design",
        "Problem Understanding",
        "Implementation Quality",
        "Code Quality",
        "Testing Discipline",
        "Development Process",
        "Communication",
        "Reflection & Ownership",
    }
    assert any(
        isinstance(citation, dict) and citation.get("dimensionKey")
        for day_score in report["dayScores"]
        for citation in day_score["evidence"]
    )
    assert {
        citation.get("dimensionKey")
        for day_score in report["dayScores"]
        for citation in day_score["evidence"]
        if isinstance(citation, dict) and citation.get("dimensionKey")
    }.issuperset(
        {
            "architectural_coherence",
            "scope_control",
            "implementation_discipline",
            "testing_discipline",
            "code_quality",
            "dependency_hygiene",
            "communication_handoff_demo",
            "evidence_trail_traceability",
            "reflection_self_awareness",
            "growth_orientation",
        }
    )
    assert any(
        citation.get("artifact_ref") == "day1-design-doc.md:L1-L20"
        for citation in report["citations"]
    )
    assert any(
        citation.get("artifact_ref") == "[00:00-02:00]"
        for citation in report["citations"]
    )
    forbidden_phrases = (
        "reject",
        "fail",
        "failed",
        "not good enough",
        "do not hire",
        "no hire",
    )
    narrative_text = " ".join(
        str(report.get(field) or "")
        for field in ("verdictOneLiner", "narrativeAssessment")
    ).lower()
    assert not any(phrase in narrative_text for phrase in forbidden_phrases)
    for reviewer_report in report["reviewerReports"]:
        assert reviewer_report["dimensionalScores"]
        assert len(reviewer_report["dimensionalScores"]) >= 8
        assert reviewer_report["strengths"]
        assert reviewer_report["concerns"]
    await _assert_evidence_links(
        reviewer_reports=report["reviewerReports"],
    )

    submission_texts = (
        (await async_session.execute(select(Submission.content_text))).scalars().all()
    )
    for submission_text in submission_texts:
        if submission_text:
            _assert_no_retired_terms(str(submission_text))

    checklist_text = (
        Path(__file__).resolve().parents[3] / "YC_DEMO_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    _assert_no_retired_terms(checklist_text)


@pytest.mark.asyncio
async def test_seed_demo_citation_refs_resolve_to_seeded_artifacts(
    async_session, monkeypatch
):
    fake_github_client = FakeGithubClient()
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script,
        "_build_github_client",
        lambda _mode: fake_github_client,
    )

    await seed_demo_script._main_async(_seed_args())

    talent_partner = await async_session.scalar(
        select(User).where(User.email == "winoetalentpartner@gmail.com")
    )
    candidate_session = await async_session.scalar(
        select(CandidateSession).where(CandidateSession.candidate_name == "Sarah Chen")
    )
    report = await async_session.scalar(
        select(WinoeReport).where(
            WinoeReport.candidate_session_id == candidate_session.id
        )
    )
    assert talent_partner is not None
    assert candidate_session is not None
    assert report is not None

    citation_payload = await get_report_citations(
        async_session,
        report_id=report.id,
        user=talent_partner,
    )
    citations = citation_payload["citations"]
    citation_by_ref = {citation["artifact_ref"]: citation for citation in citations}

    day1_submission = await async_session.scalar(
        select(Submission)
        .join(Task, Task.id == Submission.task_id)
        .where(
            Submission.candidate_session_id == candidate_session.id,
            Task.day_index == 1,
        )
    )
    day5_submission = await async_session.scalar(
        select(Submission)
        .join(Task, Task.id == Submission.task_id)
        .where(
            Submission.candidate_session_id == candidate_session.id,
            Task.day_index == 5,
        )
    )
    day4_submission = await async_session.scalar(
        select(Submission)
        .join(Task, Task.id == Submission.task_id)
        .where(
            Submission.candidate_session_id == candidate_session.id,
            Task.day_index == 4,
        )
    )
    recording = await async_session.scalar(
        select(RecordingAsset).where(
            RecordingAsset.candidate_session_id == candidate_session.id
        )
    )
    transcript = await async_session.scalar(
        select(Transcript).where(Transcript.recording_id == recording.id)
    )
    workspace = await async_session.scalar(
        select(Workspace).where(Workspace.candidate_session_id == candidate_session.id)
    )
    assert day1_submission is not None
    assert day4_submission is not None
    assert day5_submission is not None
    assert recording is not None
    assert transcript is not None
    assert workspace is not None

    day1_ref = next(
        ref for ref in citation_by_ref if ref.startswith("day1-design-doc.md")
    )
    day5_ref = next(
        ref for ref in citation_by_ref if ref.startswith("day5-reflection.md")
    )
    day1_citation = citation_by_ref[day1_ref]
    day5_citation = citation_by_ref[day5_ref]
    day4_citation = citation_by_ref["[00:00-02:00]"]
    assert str(day1_submission.id) in day1_citation["view_url"]
    assert str(day4_submission.id) in day4_citation["view_url"]
    assert str(day5_submission.id) in day5_citation["view_url"]
    day1_range = re.search(r":L(\d+)-L(\d+)$", day1_ref)
    day5_range = re.search(r":L(\d+)-L(\d+)$", day5_ref)
    assert day1_range is not None
    assert day5_range is not None
    assert day1_citation["view_url"] == f"/api/submissions/{day1_submission.id}"
    assert day1_citation["artifact_range"] == (
        f"L{day1_range.group(1)}-L{day1_range.group(2)}"
    )
    assert day4_citation["view_url"] == f"/api/submissions/{day4_submission.id}"
    assert day4_citation["artifact_range"] == "00:00-02:00"
    assert day5_citation["view_url"] == f"/api/submissions/{day5_submission.id}"
    assert day5_citation["artifact_range"] == (
        f"L{day5_range.group(1)}-L{day5_range.group(2)}"
    )

    day1_text = day1_submission.content_text or ""
    day5_text = day5_submission.content_text or ""
    assert "Use a small FastAPI service" in _line_slice(
        day1_text, int(day1_range.group(1)), int(day1_range.group(2))
    )
    assert "I used automation to accelerate the repetitive parts" in day5_text
    assert "## What Went Well" in _line_slice(
        day5_text, int(day5_range.group(1)), int(day5_range.group(2))
    )

    assert recording.id == day4_submission.content_json["transcriptRecordingId"]
    assert transcript.text
    assert transcript.segments_json
    assert any(
        isinstance(segment, dict) and segment.get("text")
        for segment in transcript.segments_json
    )

    repo_full_name = workspace.repo_full_name
    for citation in citations:
        ref = citation["artifact_ref"]
        resolved = citation["view_url"]
        assert isinstance(resolved, str) and resolved
        assert citation["resolved_open_target"] == resolved
        assert citation["artifact_range"] is not None
        if ref.startswith("["):
            assert citation["artifact_type"] == "transcript"
            assert resolved == f"/api/submissions/{day4_submission.id}"
            continue
        if (
            ref.startswith("day1")
            or ref.startswith("day3")
            or ref.startswith("day4")
            or ref.startswith("day5")
        ):
            submission = (
                day1_submission
                if ref.startswith("day1")
                else day5_submission
                if ref.startswith("day5")
                else day4_submission
                if ref.startswith("day4")
                else await async_session.scalar(
                    select(Submission)
                    .join(Task, Task.id == Submission.task_id)
                    .where(
                        Submission.candidate_session_id == candidate_session.id,
                        Task.day_index == 3,
                    )
                )
            )
            assert submission is not None
            range_match = re.search(r":L(\d+)-L(\d+)$", ref)
            assert range_match is not None
            start_line = int(range_match.group(1))
            end_line = int(range_match.group(2))
            assert resolved == f"/api/submissions/{submission.id}"
            if ref.startswith("day1") or ref.startswith("day5"):
                snippet = _line_slice(
                    submission.content_text or "", start_line, end_line
                )
                assert snippet.strip()
            continue
        commit_sha, path_and_range = ref.split(":", 1)
        path = path_and_range.split(":L", 1)[0]
        commit = await fake_github_client.get_commit(repo_full_name, commit_sha)
        assert commit["message"] != "demo commit"
        compare_base = commit["parents"][0]["sha"] if commit["parents"] else "base"
        compare = await fake_github_client.get_compare(
            repo_full_name, compare_base, commit_sha
        )
        assert any(file["filename"] == path for file in compare["files"])


@pytest.mark.asyncio
async def test_seed_demo_active_candidate_day_two_path_dispatches_and_resolves(
    async_session, monkeypatch
):
    fake_github_client = FakeGithubClient()
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script,
        "_build_github_client",
        lambda _mode: fake_github_client,
    )

    await seed_demo_script._main_async(_seed_args())

    nina = await async_session.scalar(
        select(CandidateSession)
        .options(selectinload(CandidateSession.trial))
        .where(CandidateSession.candidate_name == "Nina Alvarez")
    )
    assert nina is not None
    day2_task = await async_session.scalar(
        select(Task)
        .join(Trial, Trial.id == Task.trial_id)
        .where(Trial.id == nina.trial_id, Task.day_index == 2)
    )
    assert day2_task is not None
    workspace = await async_session.scalar(
        select(Workspace).where(
            Workspace.candidate_session_id == nina.id, Workspace.task_id == day2_task.id
        )
    )
    assert workspace is not None

    async def _noop_async(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_codespace_status_service.cs_service.require_active_window",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_codespace_status_service.ensure_day_flow_open",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_run_tests_service.cs_service.require_active_window",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_run_tests_service.ensure_day_flow_open",
        _noop_async,
    )

    (
        codespace_workspace,
        last_test_summary,
        codespace_url,
        task,
    ) = await codespace_status(
        async_session,
        candidate_session=nina,
        task_id=day2_task.id,
        github_client=fake_github_client,
    )
    assert task.id == day2_task.id
    assert codespace_workspace.repo_full_name == workspace.repo_full_name
    assert codespace_workspace.codespace_state == "available"
    assert codespace_url
    assert last_test_summary is None

    runner = GithubActionsRunner(
        fake_github_client,
        workflow_file="winoe-evidence-capture.yml",
        poll_interval_seconds=0.0,
        max_poll_seconds=1.0,
    )
    dispatch_task, dispatch_workspace, run_result = await run_task_tests(
        async_session,
        candidate_session=nina,
        task_id=day2_task.id,
        runner=runner,
        branch=None,
        workflow_inputs={"candidateSessionId": str(nina.id)},
    )
    assert dispatch_task.id == day2_task.id
    assert dispatch_workspace.repo_full_name == workspace.repo_full_name
    assert run_result.status == "passed"
    assert run_result.raw and run_result.raw.get("status") == "completed"
    assert run_result.raw.get("conclusion") == "success"
    assert run_result.run_id > 0


@pytest.mark.asyncio
async def test_seed_demo_rerun_clears_finalized_task_drafts_before_submissions(
    async_session, monkeypatch
):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    args = _seed_args()
    await seed_demo_script._main_async(args)

    submission = await async_session.scalar(select(Submission).order_by(Submission.id))
    assert submission is not None
    finalized_at = datetime.now(UTC)
    async_session.add(
        TaskDraft(
            candidate_session_id=submission.candidate_session_id,
            task_id=submission.task_id,
            content_text="finalized demo draft",
            finalized_at=finalized_at,
            finalized_submission_id=submission.id,
        )
    )
    await async_session.commit()

    await seed_demo_script._main_async(args)

    task_draft_count = await async_session.scalar(
        select(func.count()).select_from(TaskDraft)
    )
    submission_count = await async_session.scalar(
        select(func.count()).select_from(Submission)
    )
    assert task_draft_count == 0
    assert submission_count == 6


@pytest.mark.asyncio
async def test_seed_demo_cli_accepts_custom_talent_partner_email_and_lists_trials(
    async_client, async_session, monkeypatch
):
    custom_email = "winoetalentpartner@gmail.com"
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    await seed_demo_script._main_async(
        _seed_args(
            talent_partner_email=custom_email,
            talent_partner_name="TalentPartner",
            company_name="Northstar Labs",
        )
    )

    talent_partner = await async_session.scalar(
        select(User).where(User.email == custom_email)
    )
    assert talent_partner is not None
    assert talent_partner.name == "TalentPartner"

    allowed_statuses = {"not_started", "in_progress", "completed", "expired"}
    active_trial = await async_session.scalar(
        select(Trial).where(Trial.title == "Senior Backend Engineer Trial")
    )
    awaiting_trial = await async_session.scalar(
        select(Trial).where(Trial.title == "Staff Engineer Trial")
    )
    assert active_trial is not None
    assert awaiting_trial is not None

    active_res = await async_client.get(
        f"/api/trials/{active_trial.id}/candidates",
        headers={"x-dev-user-email": custom_email},
    )
    awaiting_res = await async_client.get(
        f"/api/trials/{awaiting_trial.id}/candidates",
        headers={"x-dev-user-email": custom_email},
    )
    assert active_res.status_code == 200
    assert awaiting_res.status_code == 200

    active_rows = active_res.json()
    awaiting_rows = awaiting_res.json()
    assert active_rows
    assert awaiting_rows
    assert {row["status"] for row in active_rows} == {"in_progress"}
    assert {row["status"] for row in awaiting_rows} == {"not_started"}
    assert all(row["status"] in allowed_statuses for row in active_rows)
    assert all(row["status"] in allowed_statuses for row in awaiting_rows)


@pytest.mark.asyncio
async def test_demo_rerun_preserves_non_demo_rows(async_session, monkeypatch):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    await seed_demo_script._main_async(_seed_args())

    other_partner = await create_talent_partner(
        async_session,
        email="operator@acme.example",
        company_name="Acme Research",
        name="Acme Operator",
    )
    other_trial, _other_tasks = await create_trial(
        async_session,
        created_by=other_partner,
        title="Non Demo Trial",
        role="Backend Engineer",
        focus="Outside the demo scope",
        company_context={"demoMode": "not-demo"},
    )
    now = datetime.now(UTC)
    other_candidate_session = await create_candidate_session(
        async_session,
        trial=other_trial,
        candidate_name="Other Candidate",
        invite_email="other@example.com",
        candidate_email="other@example.com",
        status="completed",
        completed_at=now,
        started_at=now,
    )
    await create_run_with_day_scores(
        async_session,
        candidate_session_id=other_candidate_session.id,
        scenario_version_id=other_candidate_session.scenario_version_id,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="demo",
        rubric_version="demo",
        day2_checkpoint_sha="a" * 40,
        day3_final_sha="b" * 40,
        cutoff_commit_sha="b" * 40,
        transcript_reference="transcript:other",
        day_scores=[
            {
                "day_index": 1,
                "score": 0.5,
                "rubric_results_json": {"signal": 0.5},
                "evidence_pointers_json": [],
            }
        ],
        overall_winoe_score=0.5,
        recommendation="positive_signal",
        confidence=0.5,
        generated_at=now,
        raw_report_json={"overallWinoeScore": 0.5, "dimensions": [], "citations": []},
        status="completed",
        started_at=now,
        completed_at=now,
        commit=False,
    )
    await upsert_marker(
        async_session,
        candidate_session_id=other_candidate_session.id,
        generated_at=now,
        commit=False,
    )
    await async_session.commit()

    await seed_demo_script._main_async(_seed_args())

    other_company_count = await async_session.scalar(
        select(func.count()).select_from(Company).where(Company.name == "Acme Research")
    )
    other_user_count = await async_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.email == "operator@acme.example")
    )
    demo_company_count = await async_session.scalar(
        select(func.count())
        .select_from(Company)
        .where(Company.name == "Northstar Labs")
    )
    demo_user_count = await async_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.email == "winoetalentpartner@gmail.com")
    )

    assert other_company_count == 1
    assert other_user_count == 1
    assert demo_company_count == 1
    assert demo_user_count == 1


@pytest.mark.asyncio
async def test_seed_demo_reset_path_prints_full_reset_and_calls_reset_database(
    async_session, monkeypatch, capsys
):
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    called = []

    async def _fake_drop(_engine):
        called.append("drop")

    async def _fake_reset(_engine):
        called.append("reset")

    def _fake_migrations(_root):
        called.append("migrations")

    monkeypatch.setattr(seed_demo_script, "_drop_existing_schema", _fake_drop)
    monkeypatch.setattr(seed_demo_script, "_run_migrations", _fake_migrations)
    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)

    await seed_demo_script._main_async(_seed_args(reset_db=True))

    output = capsys.readouterr().out
    assert "full database reset requested" in output
    assert "using GitHub provider=fake" in output
    assert called == ["drop", "migrations", "reset"]


def test_fake_provider_mode_uses_fake_client_without_real_credentials(monkeypatch):
    class _RealClientShouldNotBeConstructed:
        def __init__(self, *args, **kwargs):
            raise AssertionError("real GitHub client should not be constructed")

    monkeypatch.setattr(
        seed_demo_script, "GithubClient", _RealClientShouldNotBeConstructed
    )
    client = seed_demo_script._build_github_client("fake")
    assert isinstance(client, FakeGithubClient)


def test_seed_demo_defaults_local_qa_runtime_environment(monkeypatch):
    env_names = (*seed_demo_script._DEMO_RUNTIME_ENV_VARS, "GITHUB_PROVIDER")
    previous = {name: os.environ.get(name) for name in env_names}
    try:
        for name in env_names:
            monkeypatch.delenv(name, raising=False)

        seed_demo_script._default_demo_runtime_environment()

        assert all(
            os.environ[name] == "demo"
            for name in seed_demo_script._DEMO_RUNTIME_ENV_VARS
        )
        assert os.environ["GITHUB_PROVIDER"] == "fake"
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_real_provider_mode_requires_github_config(monkeypatch):
    monkeypatch.setattr(seed_demo_script.settings.github, "GITHUB_ORG", "")
    monkeypatch.setattr(seed_demo_script.settings.github, "GITHUB_TOKEN", "")

    with pytest.raises(RuntimeError, match="WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN"):
        seed_demo_script._build_github_client("real")


@pytest.mark.asyncio
async def test_seed_demo_main_with_cleanup_disposes_engine(monkeypatch):
    calls: list[str] = []

    async def _fake_main(_args):
        calls.append("main")

    class _Engine:
        async def dispose(self):
            calls.append("dispose")

    monkeypatch.setattr(seed_demo_script, "_main_async", _fake_main)
    monkeypatch.setattr(seed_demo_script, "engine", _Engine())

    await seed_demo_script._main_with_cleanup(SimpleNamespace())

    assert calls == ["main", "dispose"]


def test_demo_seed_reset_is_blocked_in_production_like_env(monkeypatch):
    monkeypatch.setenv("WINOE_ENV", "production")
    with pytest.raises(RuntimeError, match="production-like environment"):
        seed_demo_script._ensure_safe_environment(
            reset_requested=True, allow_production_write=False
        )


@pytest.mark.asyncio
async def test_real_provider_validation_happens_before_reset(monkeypatch):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)

    called = {"reset": False}

    async def _fake_reset(_engine):
        called["reset"] = True

    def _raise_missing_creds(_mode):
        raise RuntimeError(
            "Real GitHub provider mode requires WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN."
        )

    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)
    monkeypatch.setattr(seed_demo_script, "_build_github_client", _raise_missing_creds)

    with pytest.raises(RuntimeError, match="WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN"):
        await seed_demo_script._main_async(
            _seed_args(reset_db=True, github_provider="real")
        )

    assert called["reset"] is False


@pytest.mark.asyncio
async def test_real_provider_org_preflight_happens_before_reset(monkeypatch):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)

    called = {"reset": False}

    async def _fake_reset(_engine):
        called["reset"] = True

    class _RealClientStub:
        async def get_authenticated_user_login(self):
            return "demo-user"

        async def _get_json(self, _path):
            raise RuntimeError("GitHub API error (404)")

    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: _RealClientStub()
    )

    with pytest.raises(RuntimeError, match="GitHub API error"):
        await seed_demo_script._main_async(
            _seed_args(reset_db=True, github_provider="real")
        )

    assert called["reset"] is False


def test_checklist_contains_seed_command_and_current_winoe_language():
    checklist_text = (
        Path(__file__).resolve().parents[3] / "YC_DEMO_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    assert "export WINOE_ENV=local" in checklist_text
    assert "export WINOE_DEMO_MODE=true" in checklist_text
    assert "WINOE_AI_RUNTIME_MODE=demo" in checklist_text
    assert "GITHUB_PROVIDER=fake" in checklist_text
    assert "./scripts/seed_demo.sh" in checklist_text
    assert "http://localhost:3000/login" in checklist_text
    assert "http://localhost:3000/talent-partner/trials" in checklist_text
    assert "Talent Partner" in checklist_text
    assert "Evidence Trail" in checklist_text
    assert "Winoe Report" in checklist_text
    assert "Winoe Score" in checklist_text
    _assert_no_retired_terms(checklist_text)


@pytest.mark.asyncio
async def test_clear_demo_scope_nulls_trial_fk_before_scenario_version_delete(
    monkeypatch,
):
    from app.demo.services.yc_demo_seed_service import _clear_demo_scope

    class _ScalarResult:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return self

        def all(self):
            return list(self._values)

    class _RecordingSession:
        def __init__(self):
            self.calls = []

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            stmt_text = str(stmt)
            self.calls.append(stmt_text)
            if "SELECT users.id" in stmt_text:
                return _ScalarResult([2])
            if "SELECT trials.id" in stmt_text:
                return _ScalarResult([SimpleNamespace(id=11, company_id=1)])
            if "SELECT candidate_sessions.id" in stmt_text:
                return _ScalarResult([21])
            if "SELECT scenario_versions.id" in stmt_text:
                return _ScalarResult([31])
            if "SELECT tasks.id" in stmt_text:
                return _ScalarResult([41])
            if "SELECT workspaces.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT workspace_groups.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT evaluation_runs.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT recording_assets.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT jobs.id" in stmt_text:
                return _ScalarResult([])
            return _ScalarResult([])

        async def commit(self):
            self.calls.append("COMMIT")

    session = _RecordingSession()
    config = SimpleNamespace(
        trial_title="Senior Frontend Engineer Trial",
        company_name="Northstar Labs",
        talent_partner_email="winoetalentpartner@gmail.com",
    )
    await _clear_demo_scope(session, config)

    trial_update_index = next(
        i for i, call in enumerate(session.calls) if "UPDATE trials" in call
    )
    evaluation_state_delete_index = next(
        i
        for i, call in enumerate(session.calls)
        if "DELETE FROM trial_evaluation_states" in call
    )
    candidate_session_delete_index = next(
        i
        for i, call in enumerate(session.calls)
        if "DELETE FROM candidate_sessions" in call
    )
    scenario_delete_index = next(
        i
        for i, call in enumerate(session.calls)
        if "DELETE FROM scenario_versions" in call
    )
    trial_delete_index = next(
        i for i, call in enumerate(session.calls) if "DELETE FROM trials" in call
    )
    user_delete_index = next(
        i for i, call in enumerate(session.calls) if "DELETE FROM users" in call
    )
    assert evaluation_state_delete_index < candidate_session_delete_index
    assert trial_update_index < scenario_delete_index
    assert trial_delete_index < user_delete_index


@pytest.mark.asyncio
async def test_clear_demo_scope_preserves_user_with_non_demo_trial(async_session):
    from app.demo.services.yc_demo_seed_service import _clear_demo_scope

    user = await create_talent_partner(
        async_session,
        email="winoetalentpartner@gmail.com",
    )
    demo_trial, _ = await create_trial(
        async_session,
        created_by=user,
        title="Senior Frontend Engineer Trial",
        company_context={"demoMode": "yc-demo"},
    )
    non_demo_trial, _ = await create_trial(
        async_session,
        created_by=user,
        title="Customer Trial",
        company_context={"demoMode": "customer-data"},
    )
    await async_session.commit()

    await _clear_demo_scope(
        async_session,
        SimpleNamespace(
            trial_title="Senior Frontend Engineer Trial",
            company_name="Northstar Labs",
            talent_partner_email="winoetalentpartner@gmail.com",
        ),
    )

    assert (
        await async_session.scalar(select(User).where(User.id == user.id))
    ) is not None
    assert (
        await async_session.scalar(select(Trial).where(Trial.id == non_demo_trial.id))
    ) is not None
    assert (
        await async_session.scalar(select(Trial).where(Trial.id == demo_trial.id))
    ) is None


@pytest.mark.asyncio
async def test_seed_demo_reuses_preserved_company_and_user_with_non_demo_trial(
    async_session,
):
    from app.demo.services.yc_demo_seed_service import (
        DemoSeedConfig,
        seed_yc_demo_dataset,
    )

    company = Company(name="Northstar Labs")
    async_session.add(company)
    await async_session.flush()
    user = User(
        name="Existing Talent Partner",
        email="winoetalentpartner@gmail.com",
        role="talent_partner",
        company_id=company.id,
        password_hash="",
    )
    async_session.add(user)
    await async_session.flush()
    non_demo_trial, _ = await create_trial(
        async_session,
        created_by=user,
        title="Customer Trial",
        company_context={"demoMode": "customer-data"},
    )
    await async_session.commit()

    await seed_yc_demo_dataset(
        async_session,
        config=DemoSeedConfig(),
        github_client=FakeGithubClient(),
    )

    company_count = await async_session.scalar(
        select(func.count())
        .select_from(Company)
        .where(Company.name == "Northstar Labs")
    )
    user_count = await async_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.email == "winoetalentpartner@gmail.com")
    )
    assert company_count == 1
    assert user_count == 1
    assert (
        await async_session.scalar(select(Trial).where(Trial.id == non_demo_trial.id))
    ) is not None
