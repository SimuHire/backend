"""Deterministic Talent Partner + Trial rows for local Task 3 browser QA."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import delete, or_, select, update

from app.candidates.candidate_sessions.repositories.candidates_candidate_sessions_repositories_candidates_candidate_sessions_candidate_session_model import (
    CandidateSession,
)
from app.config import settings
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RECOMMENDATION_STRONG_HIRE,
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationDayScore,
    EvaluationReviewerReport,
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_create_run_repository import (
    create_run,
)
from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    Transcript,
)
from app.shared.database.shared_database_models_model import (
    CandidateDayAudit,
    Company,
    NotificationDeliveryAudit,
    RecordingAsset,
    ScenarioEditAudit,
    ScenarioVersion,
    Submission,
    Task,
    TaskDraft,
    Trial,
    User,
    WinoeReport,
    WinoeRubricSnapshot,
    Workspace,
    WorkspaceGroup,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import Job
from app.trials.constants.trials_constants_trials_defaults_constants import (
    DEFAULT_TEMPLATE_KEY,
)
from app.trials.repositories.trials_repositories_trials_trial_status_constants import (
    TRIAL_STATUS_ACTIVE_INVITING,
    TRIAL_STATUS_COMPLETED,
    TRIAL_STATUS_DRAFT,
    TRIAL_STATUS_GENERATING,
    TRIAL_STATUS_READY_FOR_REVIEW,
)
from app.trials.services.trials_services_trials_scenario_versions_create_service import (
    create_initial_scenario_version,
)
from app.trials.services.trials_services_trials_task_seed_service import (
    seed_default_tasks,
)

TASK3_QA_COMPANY: Final[str] = "Winoe Task3 QA"
TASK3_ACTIVE_TITLE: Final[str] = "Senior Backend Engineer"
TASK3_AWAITING_TITLE: Final[str] = "QA Awaiting Candidate Trial"
TASK3_COMPLETED_TITLE: Final[str] = "QA Completed Cohort Trial"


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


async def _purge_task3_qa_trials_for_user(db, user_id: int) -> None:
    task3_titles = (TASK3_ACTIVE_TITLE, TASK3_AWAITING_TITLE, TASK3_COMPLETED_TITLE)
    trial_ids = (
        (
            await db.execute(
                select(Trial.id).where(
                    Trial.created_by == user_id,
                    or_(
                        Trial.title.in_(task3_titles),
                        Trial.focus == "Local Task 3 QA seed",
                        Trial.ai_notice_version == "task3-qa-v1",
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    if not trial_ids:
        return
    scenario_version_ids = (
        (
            await db.execute(
                select(ScenarioVersion.id).where(
                    ScenarioVersion.trial_id.in_(trial_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    task_ids = (
        (await db.execute(select(Task.id).where(Task.trial_id.in_(trial_ids))))
        .scalars()
        .all()
    )
    candidate_session_ids = (
        (
            await db.execute(
                select(CandidateSession.id).where(
                    CandidateSession.trial_id.in_(trial_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    evaluation_run_ids: list[int] = []
    recording_ids: list[int] = []
    if candidate_session_ids:
        evaluation_run_ids = (
            (
                await db.execute(
                    select(EvaluationRun.id).where(
                        EvaluationRun.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        recording_ids = (
            (
                await db.execute(
                    select(RecordingAsset.id).where(
                        RecordingAsset.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
    if evaluation_run_ids:
        await db.execute(
            delete(EvaluationReviewerReport).where(
                EvaluationReviewerReport.run_id.in_(evaluation_run_ids)
            )
        )
        await db.execute(
            delete(EvaluationDayScore).where(
                EvaluationDayScore.run_id.in_(evaluation_run_ids)
            )
        )
        await db.execute(
            delete(EvaluationRun).where(EvaluationRun.id.in_(evaluation_run_ids))
        )
    if task_ids:
        await db.execute(
            delete(TaskDraft).where(
                TaskDraft.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(Submission).where(
                Submission.candidate_session_id.in_(candidate_session_ids)
            )
        )
    if recording_ids:
        await db.execute(
            delete(Transcript).where(Transcript.recording_id.in_(recording_ids))
        )
        await db.execute(
            delete(RecordingAsset).where(RecordingAsset.id.in_(recording_ids))
        )
    if candidate_session_ids:
        await db.execute(
            delete(WinoeReport).where(
                WinoeReport.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(Workspace).where(
                Workspace.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(WorkspaceGroup).where(
                WorkspaceGroup.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(CandidateDayAudit).where(
                CandidateDayAudit.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(Job).where(Job.candidate_session_id.in_(candidate_session_ids))
        )
        await db.execute(
            delete(NotificationDeliveryAudit).where(
                NotificationDeliveryAudit.candidate_session_id.in_(
                    candidate_session_ids
                )
            )
        )
    if candidate_session_ids:
        await db.execute(
            delete(CandidateSession).where(
                CandidateSession.id.in_(candidate_session_ids)
            )
        )
    if task_ids:
        await db.execute(delete(Task).where(Task.id.in_(task_ids)))
    await db.execute(
        update(Trial)
        .where(Trial.id.in_(trial_ids))
        .values(
            status=TRIAL_STATUS_DRAFT,
            active_scenario_version_id=None,
            pending_scenario_version_id=None,
        )
    )
    if scenario_version_ids:
        await db.execute(
            delete(ScenarioEditAudit).where(
                ScenarioEditAudit.scenario_version_id.in_(scenario_version_ids)
            )
        )
        await db.execute(
            delete(WinoeRubricSnapshot).where(
                WinoeRubricSnapshot.scenario_version_id.in_(scenario_version_ids)
            )
        )
        await db.execute(
            delete(ScenarioVersion).where(ScenarioVersion.id.in_(scenario_version_ids))
        )
    await db.execute(
        delete(NotificationDeliveryAudit).where(
            NotificationDeliveryAudit.trial_id.in_(trial_ids)
        )
    )
    await db.execute(delete(Trial).where(Trial.id.in_(trial_ids)))


async def purge_task3_local_qa(db, *, talent_partner_email: str) -> None:
    """Remove Task 3 QA trials owned by the Talent Partner email."""
    email = talent_partner_email.strip().lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        return
    await _purge_task3_qa_trials_for_user(db, int(user.id))


def _trial_shell(
    *,
    company_id: int,
    user_id: int,
    title: str,
    role: str,
    status: str,
) -> Trial:
    return Trial(
        company_id=company_id,
        title=title,
        role=role,
        preferred_language_framework="Python, FastAPI, PostgreSQL",
        seniority="Senior",
        focus="Local Task 3 QA seed",
        company_context={
            "companyName": TASK3_QA_COMPANY,
            "preferredLanguageFramework": "Python, FastAPI, PostgreSQL",
            "qaSeed": "task3-local",
        },
        company_rubric_json=None,
        ai_prompt_overrides_json=None,
        ai_notice_version="task3-qa-v1",
        ai_notice_text="Local QA seed notice.",
        scenario_template="",
        template_key=DEFAULT_TEMPLATE_KEY,
        created_by=user_id,
        status=status,
        generating_at=_now() if status == TRIAL_STATUS_GENERATING else None,
    )


async def _add_scenario(db, trial: Trial) -> tuple[ScenarioVersion, list[Task]]:
    tasks = await seed_default_tasks(db, trial.id, trial.template_key)
    await db.flush()
    scenario = await create_initial_scenario_version(db, trial=trial, tasks=tasks)
    return scenario, tasks


async def _add_candidate(
    db,
    *,
    trial: Trial,
    scenario_version_id: int,
    invite_email: str,
    candidate_name: str,
    status: str,
) -> CandidateSession:
    tok = f"task3qa-{trial.id}-{invite_email}"
    cs = CandidateSession(
        trial_id=trial.id,
        scenario_version_id=scenario_version_id,
        candidate_name=candidate_name,
        invite_email=invite_email,
        candidate_email=invite_email,
        candidate_auth0_email=invite_email,
        token=tok,
        status=status,
        invite_email_status="sent",
        invite_email_sent_at=_now(),
        candidate_timezone="America/New_York",
        consent_version="task3-qa-v1",
        consent_timestamp=_now(),
        ai_notice_version="task3-qa-v1",
    )
    db.add(cs)
    await db.flush()
    return cs


async def seed_task3_local_qa(db, *, talent_partner_email: str) -> None:
    """Create three dashboard rows: Active (3+ candidates), Awaiting (0), Completed."""
    if settings.is_production_environment():
        raise RuntimeError("task3 local QA seed is not allowed in production.")

    email = talent_partner_email.strip().lower()
    user = await db.scalar(select(User).where(User.email == email))
    company = None
    if user is not None and user.company_id is not None:
        company = await db.scalar(select(Company).where(Company.id == user.company_id))
    if company is None:
        company = await db.scalar(
            select(Company).where(Company.name == TASK3_QA_COMPANY)
        )
        if company is None:
            company = Company(name=TASK3_QA_COMPANY)
            db.add(company)
            await db.flush()

    if user is None:
        user = User(
            name="QA Talent Partner",
            email=email,
            role="talent_partner",
            company_id=company.id,
            password_hash="",
        )
        db.add(user)
        await db.flush()
    elif user.company_id is None:
        user.company_id = company.id
        await db.flush()
    else:
        user.role = "talent_partner"
        await db.flush()

    await purge_task3_local_qa(db, talent_partner_email=email)

    # 1) Active — 3 in-flight candidates, no score range yet
    t_active = _trial_shell(
        company_id=company.id,
        user_id=user.id,
        title=TASK3_ACTIVE_TITLE,
        role="Backend Engineer",
        status=TRIAL_STATUS_GENERATING,
    )
    db.add(t_active)
    await db.flush()
    scen_a, _tasks_a = await _add_scenario(db, t_active)
    t_active.status = TRIAL_STATUS_ACTIVE_INVITING
    t_active.activated_at = _now()
    for i in range(3):
        await _add_candidate(
            db,
            trial=t_active,
            scenario_version_id=scen_a.id,
            invite_email=f"task3-active-{i}@example.com",
            candidate_name=f"Active Candidate {i + 1}",
            status="in_progress",
        )

    # 2) Awaiting Candidate — approved scenario, zero invites
    t_wait = _trial_shell(
        company_id=company.id,
        user_id=user.id,
        title=TASK3_AWAITING_TITLE,
        role="Platform Engineer",
        status=TRIAL_STATUS_GENERATING,
    )
    db.add(t_wait)
    await db.flush()
    await _add_scenario(db, t_wait)
    t_wait.status = TRIAL_STATUS_READY_FOR_REVIEW
    t_wait.ready_for_review_at = _now()

    # 3) Completed cohort — two finished evaluations → score range on list API
    t_done = _trial_shell(
        company_id=company.id,
        user_id=user.id,
        title=TASK3_COMPLETED_TITLE,
        role="Staff Engineer",
        status=TRIAL_STATUS_GENERATING,
    )
    db.add(t_done)
    await db.flush()
    scen_d, _tasks_d = await _add_scenario(db, t_done)
    t_done.status = TRIAL_STATUS_ACTIVE_INVITING
    t_done.activated_at = _now() - timedelta(days=2)
    scores = (0.72, 0.91)
    for i, sc in enumerate(scores):
        cs = await _add_candidate(
            db,
            trial=t_done,
            scenario_version_id=scen_d.id,
            invite_email=f"task3-done-{i}@example.com",
            candidate_name=f"Completed Candidate {i + 1}",
            status="completed",
        )
        cs.completed_at = _now() - timedelta(days=1)
        await create_run(
            db,
            candidate_session_id=cs.id,
            scenario_version_id=scen_d.id,
            model_name="qa-seed",
            model_version="1",
            prompt_version="1",
            rubric_version="1",
            day2_checkpoint_sha="0" * 40,
            day3_final_sha="1" * 40,
            cutoff_commit_sha="1" * 40,
            transcript_reference="task3:qa",
            overall_winoe_score=sc,
            recommendation=EVALUATION_RECOMMENDATION_STRONG_HIRE,
            confidence=0.85,
            raw_report_json={"overallWinoeScore": sc},
            status=EVALUATION_RUN_STATUS_COMPLETED,
            started_at=_now() - timedelta(hours=2),
            completed_at=_now() - timedelta(hours=1),
            commit=False,
        )
    t_done.status = TRIAL_STATUS_COMPLETED

    await db.commit()


__all__ = [
    "TASK3_ACTIVE_TITLE",
    "TASK3_AWAITING_TITLE",
    "TASK3_COMPLETED_TITLE",
    "purge_task3_local_qa",
    "seed_task3_local_qa",
]
