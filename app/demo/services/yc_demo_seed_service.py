"""YC demo seed helpers for creating a deterministic golden-path dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.candidates.candidate_sessions.repositories.candidates_candidate_sessions_repositories_candidates_candidate_sessions_day_audit_model import (
    CandidateDayAudit,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RECOMMENDATION_HIRE,
    EVALUATION_RECOMMENDATION_STRONG_HIRE,
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationDayScore,
    EvaluationReviewerReport,
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_create_run_repository import (
    create_run,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_day_scores_repository import (
    add_day_scores,
)
from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationState,
    TrialEvaluationStateRecord,
)
from app.integrations.github import FakeGithubClient, GithubClient
from app.notifications.repositories.notifications_repositories_notifications_delivery_audits_core_model import (
    NotificationDeliveryAudit,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Company,
    RecordingAsset,
    Submission,
    Task,
    TaskDraft,
    Transcript,
    Trial,
    User,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    Job,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_core_model import (
    Workspace,
    WorkspaceGroup,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_citation_repository import (
    replace_report_citations,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_repository import (
    upsert_marker,
)
from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
    bootstrap_empty_candidate_repo,
)
from app.trials.constants.trials_constants_trials_defaults_constants import (
    DEFAULT_TEMPLATE_KEY,
)
from app.trials.repositories.scenario_versions.trials_repositories_scenario_versions_trials_scenario_versions_model import (
    ScenarioVersion as TrialScenarioVersion,
)
from app.trials.repositories.trials_repositories_trials_trial_status_constants import (
    TRIAL_STATUS_ACTIVE_INVITING,
    TRIAL_STATUS_COMPLETED,
    TRIAL_STATUS_GENERATING,
    TRIAL_STATUS_READY_FOR_REVIEW,
)
from app.trials.services.trials_services_trials_scenario_versions_create_service import (
    create_initial_scenario_version,
)
from app.trials.services.trials_services_trials_task_seed_service import (
    seed_default_tasks,
)


@dataclass(slots=True)
class DemoSeedConfig:
    """Configuration for the YC demo seed."""

    talent_partner_email: str = "winoetalentpartner@gmail.com"
    talent_partner_name: str = "Maya Chen"
    company_name: str = "Northstar Labs"
    trial_title: str = "Senior Frontend Engineer Trial"
    trial_role: str = "Senior Frontend Engineer"
    trial_seniority: str = "senior"
    trial_focus: str = (
        "Design and ship a from-scratch product surface for a candidate work Trial."
    )
    trial_preferred_language_framework: str = "TypeScript + React"
    git_owner: str = "winoe-ai-demo"
    repo_prefix: str = "winoe-ws-"
    codespace_workspace_key: str = "coding"
    timezone: str = "America/New_York"
    qa_candidate_email: str = "winoecandidate@gmail.com"
    reset_db: bool = False


@dataclass(slots=True)
class DemoCandidateProfile:
    """Deterministic profile for one demo candidate."""

    label: str
    name: str
    email: str
    repo_suffix: str
    overall_score: float
    confidence: float
    recommendation: str
    internal_recommendation: str
    strength_points: list[str]
    concern_points: list[str]
    summary_line: str
    day_scores: dict[int, float]
    test_summary: dict[str, tuple[int, int]]


@dataclass(slots=True)
class DemoInviteCandidateProfile:
    """Deterministic profile for an invited but not yet started candidate."""

    name: str
    email: str
    github_username: str


@dataclass(slots=True)
class DemoTrialProfile:
    """Seed plan for a demo Trial."""

    title: str
    role: str
    seniority: str
    preferred_language_framework: str
    focus: str
    status: str
    candidates: list[DemoInviteCandidateProfile]


@dataclass(slots=True)
class DemoSeedSummary:
    """High-level summary of the seeded demo dataset."""

    company_id: int
    trial_id: int
    candidate_session_ids: list[int]
    repo_full_names: list[str]


DEMO_MODE_MARKER = "yc-demo"
DEMO_TRIAL_TITLES = [
    "Senior Backend Engineer Trial",
    "Senior Frontend Engineer Trial",
    "Staff Engineer Trial",
]
DEMO_HERO_CANDIDATE_EMAIL = "sarah.chen.demo@winoe.ai"
DEMO_ACTIVE_CANDIDATE_EMAIL = "winoecandidate@gmail.com"
DEMO_AWAITING_CANDIDATE_EMAIL = "nina.alvarez.demo@winoe.ai"


def _apply_legacy_trial_fields(trial: Trial) -> None:
    """Keep the seeded trial compatible with existing stored columns."""
    trial.scenario_template = ""
    trial.template_key = DEFAULT_TEMPLATE_KEY


def _stable_hex(*parts: object, length: int = 40) -> str:
    seed = "\u241f".join("" if part is None else str(part) for part in parts)
    return sha256(seed.encode("utf-8")).hexdigest()[:length]


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _demo_trial_brief_markdown(config: DemoSeedConfig) -> str:
    return (
        "# Project Brief\n\n"
        "## Business Context\n\n"
        f"{config.company_name} needs a lightweight system for coordinating "
        "candidate evidence, review notes, and Trial progression.\n\n"
        "## Product Goal\n\n"
        "Build a from-scratch work Trial experience that keeps every step "
        "evidence-backed and easy to review.\n\n"
        "## Technical Constraints\n\n"
        "- Start from an empty repository.\n"
        "- Commit a devcontainer so the project is reproducible.\n"
        "- Use clear validation, idempotent writes, and readable API boundaries.\n"
        "- Keep the architecture simple enough to finish in five days.\n\n"
        "## Expected Deliverables\n\n"
        "- A stable product surface with create, read, and status endpoints.\n"
        "- Tests that prove the core workflow.\n"
        "- Documentation that explains the design and tradeoffs.\n\n"
        "## Risks\n\n"
        "- Overengineering the storage model.\n"
        "- Missing edge-case handling around duplicate requests.\n"
        "- Treating the demo as a toy instead of a real work Trial.\n"
    )


def _demo_scenario_storyline() -> str:
    return (
        "A Talent Partner needs a reliable evidence trail for a five-day "
        "from-scratch work Trial and wants to compare candidates with a clear "
        "Winoe Report."
    )


def _demo_task_prompts(tasks: list[Task]) -> list[dict[str, Any]]:
    return [
        {
            "dayIndex": task.day_index,
            "type": task.type,
            "title": task.title,
            "description": task.description,
        }
        for task in sorted(tasks, key=lambda item: item.day_index)
    ]


def _demo_candidate_profiles() -> list[DemoCandidateProfile]:
    return [
        DemoCandidateProfile(
            label="sarah-chen",
            name="Sarah Chen",
            email=DEMO_HERO_CANDIDATE_EMAIL,
            repo_suffix="sarah-chen",
            overall_score=0.78,
            confidence=0.86,
            recommendation="positive_signal",
            internal_recommendation=EVALUATION_RECOMMENDATION_STRONG_HIRE,
            strength_points=[
                "The repository stays small and readable while still covering the full Trial scope.",
                "The implementation and tests progress in a disciplined way across the build window.",
                "The handoff documents the work clearly and keeps the evidence trail easy to follow.",
            ],
            concern_points=[
                "A deeper rollback note would make the Day 3 wrap-up stronger.",
                "The Day 4 demo could call out one more edge case explicitly.",
            ],
            summary_line=(
                "Sarah shows strong from-scratch judgment, with one or two operational "
                "gaps that are easy to discuss without weakening the overall signal."
            ),
            day_scores={1: 0.79, 2: 0.77, 3: 0.80, 4: 0.78, 5: 0.76},
            test_summary={1: (16, 0), 2: (20, 0), 3: (22, 0)},
        ),
        DemoCandidateProfile(
            label="nina-alvarez",
            name="Nina Alvarez",
            email=DEMO_ACTIVE_CANDIDATE_EMAIL,
            repo_suffix="nina-alvarez",
            overall_score=0.0,
            confidence=0.0,
            recommendation="positive_signal",
            internal_recommendation=EVALUATION_RECOMMENDATION_HIRE,
            strength_points=[
                "The from-scratch repo stays tidy as the work gets underway.",
                "The Day 2 implementation kickoff is easy to follow.",
                "The active workspace keeps the demo path live and pollable.",
            ],
            concern_points=[
                "The build is intentionally unfinished so the live day flow stays visible.",
                "There is no completed report yet, by design.",
            ],
            summary_line=(
                "Nina is mid-Trial on Day 2, with enough repo progress to make the live demo concrete."
            ),
            day_scores={1: 0.71, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00},
            test_summary={1: (12, 0), 2: (0, 0), 3: (0, 0)},
        ),
    ]


def _demo_invite_candidate_profiles() -> dict[str, list[DemoInviteCandidateProfile]]:
    return {
        "awaiting_candidate": [
            DemoInviteCandidateProfile(
                name="Priya Patel",
                email=DEMO_AWAITING_CANDIDATE_EMAIL,
                github_username="priyapatel",
            )
        ],
    }


def _demo_trial_profiles(config: DemoSeedConfig) -> list[DemoTrialProfile]:
    invites = _demo_invite_candidate_profiles()
    return [
        DemoTrialProfile(
            title="Senior Backend Engineer Trial",
            role="Senior Backend Engineer",
            seniority="senior",
            preferred_language_framework="Python + FastAPI",
            focus="Build a reliable backend surface for a five-day evidence-backed Trial.",
            status="active_inviting",
            candidates=[],
        ),
        DemoTrialProfile(
            title=config.trial_title,
            role=config.trial_role,
            seniority=config.trial_seniority,
            preferred_language_framework=config.trial_preferred_language_framework,
            focus=config.trial_focus,
            status="active_inviting",
            candidates=[
                DemoInviteCandidateProfile(
                    name="Sarah Chen",
                    email=DEMO_HERO_CANDIDATE_EMAIL,
                    github_username="sarahchen",
                )
            ],
        ),
        DemoTrialProfile(
            title="Staff Engineer Trial",
            role="Staff Engineer",
            seniority="staff",
            preferred_language_framework="Go",
            focus="Keep the architecture minimal while leaving a crisp evidence trail.",
            status="active_inviting",
            candidates=invites["awaiting_candidate"],
        ),
    ]


def _candidate_repo_name(
    config: DemoSeedConfig, candidate: DemoCandidateProfile
) -> str:
    return f"{config.repo_prefix}{candidate.repo_suffix}"


def _candidate_token(config: DemoSeedConfig, candidate: DemoCandidateProfile) -> str:
    return _stable_hex(
        config.company_name, candidate.email, "candidate-token", length=32
    )


def _candidate_commit_sha(
    config: DemoSeedConfig, candidate: DemoCandidateProfile, *, day: int
) -> str:
    return _stable_hex(config.company_name, candidate.email, "commit", day, length=40)


def _candidate_recording_key(
    config: DemoSeedConfig, candidate: DemoCandidateProfile
) -> str:
    return f"demo/{config.company_name.lower().replace(' ', '-')}/{candidate.label}/day4-handoff.mp4"


async def _commit_repo_snapshot(
    github_client: GithubClient | FakeGithubClient,
    *,
    repo_full_name: str,
    branch: str,
    parent_sha: str,
    message: str,
    files: dict[str, str],
) -> str:
    """Create a deterministic multi-file commit and advance the branch."""
    tree_entries: list[dict[str, Any]] = []
    for path, content in files.items():
        blob = await github_client.create_blob(repo_full_name, content=content)
        tree_entries.append(
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"],
            }
        )
    tree = await github_client.create_tree(
        repo_full_name, tree=tree_entries, base_tree=parent_sha
    )
    commit = await github_client.create_commit(
        repo_full_name,
        message=message,
        tree=tree["sha"],
        parents=[parent_sha] if parent_sha else [],
    )
    await github_client.update_ref(
        repo_full_name,
        ref=f"heads/{branch}",
        sha=commit["sha"],
        force=True,
    )
    return str(commit["sha"])


def _hero_day2_repo_files(candidate: DemoCandidateProfile) -> dict[str, str]:
    return {
        "src/api/trials.ts": "\n".join(
            [
                "export function buildTrialSubmissionLink(trialId: string, candidateId: string) {",
                "  return `/talent-partner/trials/${trialId}/candidates/${candidateId}/submission`;",
                "}",
                "",
                "export function buildBenchmarkLink(trialId: string) {",
                "  return `/talent-partner/trials/${trialId}/benchmarks`;",
                "}",
            ]
        )
        + "\n",
        "src/components/task-sequencing.ts": "\n".join(
            [
                "export const TASK_SEQUENCE = [1, 2, 3, 4, 5] as const;",
                "",
                "export function isCodeDay(dayIndex: number) {",
                "  return dayIndex === 2 || dayIndex === 3;",
                "}",
            ]
        )
        + "\n",
        "tests/test_trials.ts": "\n".join(
            [
                "describe('trial sequencing', () => {",
                "  it('treats days 2 and 3 as coding days', () => {",
                "    expect(true).toBe(true);",
                "  });",
                "});",
            ]
        )
        + "\n",
        "README.md": (
            "# Implementation Kickoff\n\n"
            f"{candidate.summary_line}\n\n"
            "The repo still starts from scratch, but the core candidate flow is now visible.\n"
        ),
    }


def _hero_day3_repo_files(candidate: DemoCandidateProfile) -> dict[str, str]:
    return {
        "src/services/reporting.py": "\n".join(
            [
                "def build_report_summary(total_candidates: int, ready_reports: int) -> dict[str, int]:",
                "    return {",
                "        'totalCandidates': total_candidates,",
                "        'readyReports': ready_reports,",
                "    }",
                "",
                "def build_compare_entry(candidate_name: str, commit_sha: str) -> dict[str, str]:",
                "    return {",
                "        'candidateName': candidate_name,",
                "        'commitSha': commit_sha,",
                "    }",
            ]
        )
        + "\n",
        "src/services/submission_review.py": "\n".join(
            [
                "def normalize_day(day_index: int) -> int:",
                "    if day_index in (2, 3):",
                "        return day_index",
                "    return 0",
            ]
        )
        + "\n",
        "tests/test_reporting.py": "\n".join(
            [
                "def test_report_summary_tracks_candidates():",
                "    assert True",
                "",
                "def test_compare_entry_uses_commit_sha():",
                "    assert True",
            ]
        )
        + "\n",
        "docs/runbook.md": (
            "# Demo Runbook\n\n"
            f"{candidate.summary_line}\n\n"
            "Day 3 closes with a concise handoff and a clean compare snapshot.\n"
        ),
    }


def _active_day2_repo_files(candidate: DemoCandidateProfile) -> dict[str, str]:
    return {
        "src/app.py": "\n".join(
            [
                "def build_status_payload() -> dict[str, str]:",
                "    return {'status': 'in_progress', 'day': '2'}",
            ]
        )
        + "\n",
        "src/services/provisioning.py": "\n".join(
            [
                "def build_codespace_name(repo_name: str) -> str:",
                "    return f'{repo_name}-codespace'",
            ]
        )
        + "\n",
        "tests/test_app.py": "\n".join(
            [
                "def test_status_payload_is_in_progress():",
                "    assert True",
            ]
        )
        + "\n",
        "README.md": (
            "# Implementation Kickoff\n\n"
            f"{candidate.summary_line}\n\n"
            "The active workspace is ready for the Day 2 run-tests demo.\n"
        ),
    }


def _candidate_design_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 1 Design Document\n\n"
        "## Architecture\n\n"
        "Use a small FastAPI service with one core domain module, a service layer, "
        "and a repository boundary around persistence.\n\n"
        "## Stack\n\n"
        "Python, FastAPI, PostgreSQL, and a thin integration layer for artifact "
        "capture.\n\n"
        "## Tradeoffs\n\n"
        "Prefer clear boundaries over extra abstraction. Keep writes idempotent "
        "so reruns do not drift the demo state.\n\n"
        "## Testing Plan\n\n"
        "Cover the API shape, duplicate-request behavior, and the most important "
        "repository transitions.\n\n"
        "## Implementation Plan\n\n"
        "1. Create the API and persistence structure.\n"
        "2. Add the core workflow and validation.\n"
        "3. Add tests, docs, and a concise handoff.\n\n"
        "## Risks\n\n"
        f"- {candidate.concern_points[0]}\n"
        f"- {candidate.concern_points[1]}\n"
    )


def _candidate_kickoff_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 2 Implementation Kickoff\n\n"
        "## Progress\n\n"
        f"{candidate.summary_line}\n\n"
        "## Repository Shape\n\n"
        "- Devcontainer committed.\n"
        "- README explains the project brief.\n"
        "- Core API skeleton and persistence paths are in place.\n\n"
        "## Early Validation\n\n"
        "The first tests focus on the public routes, duplicate protection, and "
        "the basic evidence trail.\n"
    )


def _candidate_wrapup_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 3 Implementation Wrap-Up\n\n"
        "## Finalization\n\n"
        f"{candidate.summary_line}\n\n"
        "## Evidence\n\n"
        "- Commit progression is visible in the repo history.\n"
        "- The tests cover the main from-scratch flow.\n"
        "- The README and API notes explain how to run the system.\n\n"
        "## Final Notes\n\n"
        "The remaining gaps are small, explicit, and easy to review in the demo.\n"
    )


def _candidate_handoff_doc(candidate: DemoCandidateProfile) -> str:
    strengths = "\n".join(f"- {item}" for item in candidate.strength_points)
    concerns = "\n".join(f"- {item}" for item in candidate.concern_points)
    return (
        "# Day 4 Handoff + Demo\n\n"
        "I walked through the architecture, the evidence trail, the main tradeoffs, "
        "and the next steps for hardening the build.\n\n"
        "## Strengths\n\n"
        f"{strengths}\n\n"
        "## Areas to Watch\n\n"
        f"{concerns}\n\n"
        "## Next Steps\n\n"
        "Tighten the last operational edge cases and continue to keep the evidence "
        "trail crisp for review.\n"
    )


def _demo_company_rubrics() -> dict[str, dict[str, str]]:
    """Return company-specific rubric overrides in the snapshot contract shape."""
    return {
        "designDocReviewer": {
            "content": (
                "# Company design rubric\n\n"
                "Look for explicit architecture boundaries, tradeoffs, and a plan "
                "that can survive a five-day delivery window."
            ),
            "versionId": "company-demo-v1",
            "sourcePath": "company-rubrics/design-doc.md",
        },
        "codeImplementationReviewer": {
            "content": (
                "# Company code rubric\n\n"
                "Prefer disciplined implementation steps, test-first habits, and "
                "clear repo hygiene."
            ),
            "versionId": "company-demo-v1",
            "sourcePath": "company-rubrics/code.md",
        },
        "demoPresentationReviewer": {
            "content": (
                "# Company demo rubric\n\n"
                "Reward crisp handoff narration, accurate tradeoff framing, and "
                "specific next steps."
            ),
            "versionId": "company-demo-v1",
            "sourcePath": "company-rubrics/demo.md",
        },
        "reflectionEssayReviewer": {
            "content": (
                "# Company reflection rubric\n\n"
                "Value honest self-review, concrete follow-up ideas, and clear "
                "ownership of gaps."
            ),
            "versionId": "company-demo-v1",
            "sourcePath": "company-rubrics/reflection.md",
        },
        "winoeReport": {
            "content": (
                "# Company Winoe synthesis rubric\n\n"
                "Synthesize evidence across the five days and keep the final "
                "judgment grounded in linked artifacts."
            ),
            "versionId": "company-demo-v1",
            "sourcePath": "company-rubrics/winoe-report.md",
        },
    }


def _candidate_reflection_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 5 Reflection\n\n"
        "## What Went Well\n\n"
        f"{candidate.strength_points[0]}\n\n"
        "## What Was Hard\n\n"
        f"{candidate.concern_points[0]}\n\n"
        "## What I Would Change\n\n"
        "I would budget more time for a deeper edge-case pass and one more "
        "round of API polish.\n\n"
        "## How I Used Tools\n\n"
        "I used automation to accelerate the repetitive parts, then reviewed the "
        "outputs manually to keep the evidence trail honest.\n\n"
        "## What I Learned\n\n"
        "A small, readable system is easier to defend when the evidence is "
        "collected day by day.\n"
    )


def _demo_code_snapshot(
    *,
    candidate: DemoCandidateProfile,
    repo_full_name: str,
    commit_sha: str,
    selected_file_path: str,
    selected_file_name: str,
    selected_file_language: str,
    selected_file_content: str,
    supporting_file_path: str,
    supporting_file_name: str,
    supporting_file_language: str,
    supporting_file_content: str,
    files_changed: int,
) -> dict[str, Any]:
    file_tree = [
        {
            "path": "src",
            "name": "src",
            "type": "folder",
            "children": [
                {
                    "path": selected_file_path,
                    "name": selected_file_name,
                    "type": "file",
                    "language": selected_file_language,
                    "content": selected_file_content,
                    "changed": True,
                },
                {
                    "path": supporting_file_path,
                    "name": supporting_file_name,
                    "type": "file",
                    "language": supporting_file_language,
                    "content": supporting_file_content,
                    "changed": files_changed > 1,
                },
            ],
        }
    ]
    commit_payload = {
        "sha": commit_sha,
        "message": f"{candidate.name} implementation checkpoint",
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "filesChanged": files_changed,
        "changedFiles": [selected_file_path, supporting_file_path],
    }
    return {
        "repositorySnapshot": {
            "fileTree": file_tree,
            "commits": [commit_payload],
            "selectedFilePath": selected_file_path,
            "selectedFileContent": selected_file_content,
            "selectedFileLanguage": selected_file_language,
            "selectedFileName": selected_file_name,
        },
        "fileTree": file_tree,
        "commits": [commit_payload],
        "selectedFilePath": selected_file_path,
        "selectedFileContent": selected_file_content,
        "selectedFileLanguage": selected_file_language,
        "selectedFileName": selected_file_name,
        "repoFullName": repo_full_name,
    }


def _candidate_submissions(
    config: DemoSeedConfig,
    candidate: DemoCandidateProfile,
    *,
    repo_full_name: str,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
    recording_key: str,
) -> dict[int, dict[str, Any]]:
    return {
        1: {
            "content_text": _candidate_design_doc(candidate),
            "content_json": {
                "artifactType": "design_document",
                "candidate": candidate.name,
                "company": config.company_name,
                "summary": candidate.summary_line,
            },
            "code_repo_path": None,
            "commit_sha": None,
            "test_output": None,
            "tests_passed": None,
            "tests_failed": None,
            "diff_summary_json": None,
        },
        2: {
            "content_text": _candidate_kickoff_doc(candidate),
            "content_json": {
                "artifactType": "implementation_kickoff",
                "repoFullName": repo_full_name,
                "bootstrapCommitSha": bootstrap_commit_sha,
                "summary": candidate.summary_line,
                **_demo_code_snapshot(
                    candidate=candidate,
                    repo_full_name=repo_full_name,
                    commit_sha=day2_commit_sha,
                    selected_file_path="src/api/trials.ts",
                    selected_file_name="trials.ts",
                    selected_file_language="typescript",
                    selected_file_content="\n".join(
                        [
                            "export function buildTrialSubmissionLink(trialId: string, candidateId: string) {",
                            "  return `/talent-partner/trials/${trialId}/candidates/${candidateId}/submission`;",
                            "}",
                            "",
                            "export function buildBenchmarkLink(trialId: string) {",
                            "  return `/talent-partner/trials/${trialId}/benchmarks`;",
                            "}",
                        ]
                    ),
                    supporting_file_path="src/components/task-sequencing.ts",
                    supporting_file_name="task-sequencing.ts",
                    supporting_file_language="typescript",
                    supporting_file_content="\n".join(
                        [
                            "export const TASK_SEQUENCE = [1, 2, 3, 4, 5] as const;",
                            "",
                            "export function isCodeDay(dayIndex: number) {",
                            "  return dayIndex === 2 || dayIndex === 3;",
                            "}",
                        ]
                    ),
                    files_changed=2,
                ),
            },
            "code_repo_path": repo_full_name,
            "commit_sha": day2_commit_sha,
            "test_output": (
                f"pytest: {candidate.test_summary[1][0]} passed, "
                f"{candidate.test_summary[1][1]} failed"
            ),
            "tests_passed": candidate.test_summary[1][0],
            "tests_failed": candidate.test_summary[1][1],
            "diff_summary_json": (
                f"Added API skeleton, validation, and the first service layer for {candidate.name}."
            ),
        },
        3: {
            "content_text": _candidate_wrapup_doc(candidate),
            "content_json": {
                "artifactType": "implementation_wrap_up",
                "repoFullName": repo_full_name,
                "finalCommitSha": day3_commit_sha,
                "summary": candidate.summary_line,
                **_demo_code_snapshot(
                    candidate=candidate,
                    repo_full_name=repo_full_name,
                    commit_sha=day3_commit_sha,
                    selected_file_path="src/services/reporting.py",
                    selected_file_name="reporting.py",
                    selected_file_language="python",
                    selected_file_content="\n".join(
                        [
                            "def build_report_summary(total_candidates: int, ready_reports: int) -> dict[str, int]:",
                            "    return {",
                            "        'totalCandidates': total_candidates,",
                            "        'readyReports': ready_reports,",
                            "    }",
                            "",
                            "def build_compare_entry(candidate_name: str, commit_sha: str) -> dict[str, str]:",
                            "    return {",
                            "        'candidateName': candidate_name,",
                            "        'commitSha': commit_sha,",
                            "    }",
                        ]
                    ),
                    supporting_file_path="src/services/submission_review.py",
                    supporting_file_name="submission_review.py",
                    supporting_file_language="python",
                    supporting_file_content="\n".join(
                        [
                            "def normalize_day(day_index: int) -> int:",
                            "    if day_index in (2, 3):",
                            "        return day_index",
                            "    return 0",
                        ]
                    ),
                    files_changed=3,
                ),
            },
            "code_repo_path": repo_full_name,
            "commit_sha": day3_commit_sha,
            "test_output": (
                f"pytest: {candidate.test_summary[2][0]} passed, "
                f"{candidate.test_summary[2][1]} failed"
            ),
            "tests_passed": candidate.test_summary[2][0],
            "tests_failed": candidate.test_summary[2][1],
            "diff_summary_json": (
                f"Finished the API, tightened docs, and polished the final evidence trail for {candidate.name}."
            ),
        },
        4: {
            "content_text": _candidate_handoff_doc(candidate),
            "content_json": {
                "artifactType": "handoff_transcript",
                "recordingKey": recording_key,
                "summary": candidate.summary_line,
            },
            "code_repo_path": None,
            "commit_sha": None,
            "test_output": None,
            "tests_passed": None,
            "tests_failed": None,
            "diff_summary_json": None,
        },
        5: {
            "content_text": _candidate_reflection_doc(candidate),
            "content_json": {
                "artifactType": "reflection_essay",
                "summary": candidate.summary_line,
            },
            "code_repo_path": repo_full_name,
            "commit_sha": day3_commit_sha,
            "test_output": None,
            "tests_passed": None,
            "tests_failed": None,
            "diff_summary_json": None,
        },
    }


def _evidence_pointers(
    *,
    repo_full_name: str,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
) -> dict[int, list[dict[str, Any]]]:
    def repo_commit_url(sha: str) -> str:
        return f"https://github.com/{repo_full_name}/commit/{sha}"

    return {
        1: [
            {
                "kind": "rubric",
                "ref": "day1-design-doc.md:L12-L31",
                "excerpt": "Architecture plan, tradeoffs, and testing strategy.",
                "dayIndex": 1,
                "sourceLabel": "Day 1 — Design Doc",
                "dimensionKey": "architectural_coherence",
                "dimensionLabel": "Architectural coherence",
            },
            {
                "kind": "commit",
                "ref": f"{bootstrap_commit_sha}:README.md:L1-L24",
                "url": repo_commit_url(bootstrap_commit_sha),
                "excerpt": "Bootstrap commit created the empty repository, devcontainer, and README.",
                "dayIndex": 1,
                "sourceLabel": "Day 1 — Design Doc",
                "dimensionKey": "scope_control",
                "dimensionLabel": "Scope control",
            },
        ],
        2: [
            {
                "kind": "commit",
                "ref": f"{day2_commit_sha}:src/api/trials.ts:L40-L88",
                "url": repo_commit_url(day2_commit_sha),
                "excerpt": "Initial implementation kickoff commit.",
                "dayIndex": 2,
                "sourceLabel": "Day 2/3 — Code",
                "dimensionKey": "implementation_discipline",
                "dimensionLabel": "Implementation discipline",
            },
            {
                "kind": "submission",
                "ref": "day2-implementation-kickoff.md:L1-L18",
                "excerpt": "Kickoff tests established the core workflow shape.",
                "dayIndex": 2,
                "sourceLabel": "Day 2/3 — Code",
                "dimensionKey": "testing_discipline",
                "dimensionLabel": "Testing discipline",
            },
        ],
        3: [
            {
                "kind": "diff",
                "ref": f"{day3_commit_sha}:src/services/reporting.py:L12-L76",
                "url": repo_commit_url(day3_commit_sha),
                "excerpt": "Wrap-up commit completed the core workflow and docs.",
                "dayIndex": 3,
                "sourceLabel": "Day 2/3 — Code",
                "dimensionKey": "code_quality",
                "dimensionLabel": "Code quality",
            },
            {
                "kind": "submission",
                "ref": "day3-implementation-wrap-up.md:L1-L20",
                "excerpt": "Wrap-up test results show the final pass/fail balance.",
                "dayIndex": 3,
                "sourceLabel": "Day 2/3 — Code",
                "dimensionKey": "dependency_hygiene",
                "dimensionLabel": "Dependency hygiene",
            },
        ],
        4: [
            {
                "kind": "transcript",
                "ref": "[00:00-02:00]",
                "excerpt": "Demo transcript with architecture, tradeoffs, and next steps.",
                "dayIndex": 4,
                "startMs": 0,
                "endMs": 120000,
                "sourceLabel": "Day 4 — Handoff + Demo",
                "dimensionKey": "communication_handoff_demo",
                "dimensionLabel": "Communication / Handoff + Demo",
            },
            {
                "kind": "submission",
                "ref": "day4-handoff-demo.md:L1-L18",
                "excerpt": "Handoff transcript and demo summary.",
                "dayIndex": 4,
                "sourceLabel": "Day 4 — Handoff + Demo",
                "dimensionKey": "evidence_trail_traceability",
                "dimensionLabel": "Evidence trail traceability",
            },
        ],
        5: [
            {
                "kind": "submission",
                "ref": "day5-reflection.md:L1-L18",
                "excerpt": "Reflection essay covering what went well, what was hard, and what changed.",
                "dayIndex": 5,
                "sourceLabel": "Day 5 — Reflection",
                "dimensionKey": "reflection_self_awareness",
                "dimensionLabel": "Reflection & self-awareness",
            },
            {
                "kind": "submission",
                "ref": "day5-reflection.md:L19-L34",
                "excerpt": "Reflection quality, self-awareness, and next-step realism.",
                "dayIndex": 5,
                "sourceLabel": "Day 5 — Reflection",
                "dimensionKey": "growth_orientation",
                "dimensionLabel": "Growth orientation",
            },
        ],
    }


def _dimensional_scores(
    candidate: DemoCandidateProfile, *, day_index: int
) -> dict[str, float]:
    if candidate.label != "sarah-chen":
        return {
            "architecture": 0.78,
            "scope_control": 0.76,
            "implementation_discipline": 0.75,
            "testing_discipline": 0.74,
            "code_quality": 0.73,
            "dependency_hygiene": 0.72,
            "communication_handoff_demo": 0.76,
            "reflection_self_awareness": 0.75,
        }
    base = {
        1: {
            "architecture": 0.88,
            "scope_control": 0.86,
            "planning": 0.87,
            "evidence_trail_traceability": 0.85,
            "communication_handoff_demo": 0.84,
            "documentation": 0.86,
            "testing_discipline": 0.83,
            "judgment": 0.85,
        },
        2: {
            "architecture": 0.87,
            "scope_control": 0.84,
            "implementation_discipline": 0.88,
            "testing_discipline": 0.86,
            "code_quality": 0.85,
            "dependency_hygiene": 0.84,
            "communication_handoff_demo": 0.83,
            "judgment": 0.84,
        },
        3: {
            "architecture": 0.86,
            "scope_control": 0.85,
            "implementation_discipline": 0.89,
            "testing_discipline": 0.87,
            "code_quality": 0.88,
            "dependency_hygiene": 0.87,
            "documentation": 0.86,
            "evidence_trail_traceability": 0.85,
        },
        4: {
            "architecture": 0.84,
            "scope_control": 0.83,
            "communication_handoff_demo": 0.88,
            "judgment": 0.85,
            "delivery_clarity": 0.87,
            "evidence_trail_traceability": 0.86,
            "documentation": 0.84,
            "reflection_self_awareness": 0.83,
        },
        5: {
            "architecture": 0.82,
            "scope_control": 0.84,
            "reflection_self_awareness": 0.86,
            "growth_orientation": 0.85,
            "tooling_judgment": 0.83,
            "communication_handoff_demo": 0.82,
            "documentation": 0.81,
            "evidence_trail_traceability": 0.84,
        },
    }
    return base[day_index]


def _assessment_text(candidate: DemoCandidateProfile, *, day_index: int) -> str:
    if candidate.label == "sarah-chen":
        assessments = {
            1: "The design is practical and keeps the Trial small enough to defend.",
            2: "The kickoff moves cleanly from plan to execution without noisy scaffolding.",
            3: "The wrap-up shows disciplined implementation and a tidy closing pass.",
            4: "The handoff is calm, specific, and anchored in concrete artifacts.",
            5: "The reflection is honest about the edges and clear about what to improve next.",
        }
    else:
        assessments = {
            1: "Clear but lightweight design notes with modest detail.",
            2: "Functional kickoff with enough structure to keep moving.",
            3: "Useful wrap-up, but the evidence trail is thinner than ideal.",
            4: "Clear handoff, with fewer concrete artifacts behind the story.",
            5: "Honest reflection that names the main gaps without overclaiming.",
        }
    return assessments[day_index]


def _strengths(candidate: DemoCandidateProfile, *, day_index: int) -> list[str]:
    if candidate.label == "sarah-chen":
        strengths = {
            1: [
                "The architecture is easy to follow",
                "Tradeoffs are described plainly",
            ],
            2: [
                "The build starts in a disciplined way",
                "Tests come in early",
            ],
            3: [
                "The repository is polished and readable",
                "Documentation tracks the implementation",
            ],
            4: [
                "The handoff is calm and structured",
                "The demo maps back to evidence cleanly",
            ],
            5: [
                "The reflection is candid and specific",
                "The candidate shows strong self-review",
            ],
        }
    else:
        strengths = {
            1: [
                "The design is practical and feasible",
                "The candidate explains the main path clearly",
            ],
            2: [
                "The implementation is functional",
                "The kickoff path is easy to follow",
            ],
            3: [
                "The wrap-up documents the outcome",
                "The repo is reasonably organized",
            ],
            4: [
                "The handoff is professional and clear",
                "The demo covers the core build",
            ],
            5: [
                "The reflection is honest",
                "The candidate can name the gaps plainly",
            ],
        }
    return strengths[day_index]


def _concerns(candidate: DemoCandidateProfile, *, day_index: int) -> list[str]:
    if candidate.label == "sarah-chen":
        concerns = {
            1: [
                "Operational hardening is not fully explored",
                "A deeper rollout plan would help",
            ],
            2: [
                "Load testing is still missing",
                "The kickoff could mention failure recovery more directly",
            ],
            3: [
                "There is room for one more edge-case pass",
                "Rollback notes could be stronger",
            ],
            4: [
                "The demo could show one more negative path",
                "No major concerns beyond polish",
            ],
            5: [
                "The reflection could include one more concrete follow-up",
                "No major concerns beyond scope",
            ],
        }
    else:
        concerns = {
            1: [
                "Operational detail is thinner than ideal",
                "A few edge cases remain implicit",
            ],
            2: [
                "The testing story is narrower than the best submissions",
                "The kickoff could be more systematic",
            ],
            3: [
                "Documentation is useful but not as complete",
                "More explicit tradeoff discussion would help",
            ],
            4: [
                "The demo misses a couple of deeper tradeoffs",
                "The handoff is credible but not as layered",
            ],
            5: [
                "The reflection is honest but light on specifics",
                "The next-step plan could be more concrete",
            ],
        }
    return concerns[day_index]


def _build_report_rows(
    *,
    candidate: DemoCandidateProfile,
    repo_full_name: str,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = _evidence_pointers(
        repo_full_name=repo_full_name,
        bootstrap_commit_sha=bootstrap_commit_sha,
        day2_commit_sha=day2_commit_sha,
        day3_commit_sha=day3_commit_sha,
    )
    day_rows: list[dict[str, Any]] = []
    reviewer_rows: list[dict[str, Any]] = []
    for day_index in range(1, 6):
        day_score = candidate.day_scores[day_index]
        day_rows.append(
            {
                "day_index": day_index,
                "score": day_score,
                "rubric_results_json": {
                    "architecture": _dimensional_scores(
                        candidate, day_index=day_index
                    ).get(
                        "architecture",
                        day_score,
                    ),
                    "planning": _dimensional_scores(candidate, day_index=day_index).get(
                        "planning",
                        day_score,
                    ),
                    "implementation": _dimensional_scores(
                        candidate, day_index=day_index
                    ).get("implementation", day_score),
                    "testing": _dimensional_scores(candidate, day_index=day_index).get(
                        "testing",
                        day_score,
                    ),
                    "communication": _dimensional_scores(
                        candidate, day_index=day_index
                    ).get("communication", day_score),
                },
                "evidence_pointers_json": evidence[day_index],
            }
        )
        reviewer_rows.append(
            {
                "reviewer_agent_key": (
                    "designDocReviewer"
                    if day_index == 1
                    else "codeImplementationReviewer"
                    if day_index in {2, 3}
                    else "demoPresentationReviewer"
                    if day_index == 4
                    else "reflectionEssayReviewer"
                ),
                "day_index": day_index,
                "submission_kind": (
                    "design_document"
                    if day_index == 1
                    else "implementation"
                    if day_index in {2, 3}
                    else "handoff"
                    if day_index == 4
                    else "reflection"
                ),
                "score": day_score,
                "dimensional_scores_json": _dimensional_scores(
                    candidate, day_index=day_index
                ),
                "evidence_citations_json": evidence[day_index],
                "assessment_text": _assessment_text(candidate, day_index=day_index),
                "strengths_json": _strengths(candidate, day_index=day_index),
                "risks_json": _concerns(candidate, day_index=day_index),
            }
        )
    return day_rows, reviewer_rows


def _build_demo_report_dimensions(
    candidate: DemoCandidateProfile,
) -> list[dict[str, Any]]:
    if candidate.label != "sarah-chen":
        return [
            {
                "name": "Architecture & Design",
                "score": 0.78,
                "justification": "The Trial stays small, practical, and easy to explain.",
            },
            {
                "name": "Problem Understanding",
                "score": 0.77,
                "justification": "The work stays anchored to the five-day evidence-backed Trial.",
            },
            {
                "name": "Implementation Quality",
                "score": 0.76,
                "justification": "The build shows a steady but modest implementation cadence.",
            },
            {
                "name": "Code Quality",
                "score": 0.75,
                "justification": "The repository remains readable and lightweight.",
            },
            {
                "name": "Testing Discipline",
                "score": 0.74,
                "justification": "The test story is present, though not especially deep.",
            },
            {
                "name": "Development Process",
                "score": 0.74,
                "justification": "The cadence is usable and the handoff remains coherent.",
            },
            {
                "name": "Communication",
                "score": 0.76,
                "justification": "The handoff is direct and keeps the narrative readable.",
            },
            {
                "name": "Reflection & Ownership",
                "score": 0.75,
                "justification": "The reflection names gaps plainly and stays grounded.",
            },
        ]
    return [
        {
            "name": "Architecture & Design",
            "score": 0.88,
            "justification": "The Day 1 design doc keeps the scope small, testable, and easy to defend.",
        },
        {
            "name": "Problem Understanding",
            "score": 0.86,
            "justification": "The brief and project setup stay tightly aligned to the actual Trial problem.",
        },
        {
            "name": "Implementation Quality",
            "score": 0.89,
            "justification": "The Day 2 and Day 3 commits show steady progress without noisy scaffolding.",
        },
        {
            "name": "Code Quality",
            "score": 0.88,
            "justification": "The repository stays readable, compact, and easy to audit.",
        },
        {
            "name": "Testing Discipline",
            "score": 0.87,
            "justification": "The day-by-day test evidence shows deliberate validation rather than hand-waving.",
        },
        {
            "name": "Development Process",
            "score": 0.86,
            "justification": "The implementation cadence, commit history, and docs all point in the same direction.",
        },
        {
            "name": "Communication",
            "score": 0.88,
            "justification": "The Day 4 handoff and demo keep the explanation specific and evidence-first.",
        },
        {
            "name": "Reflection & Ownership",
            "score": 0.84,
            "justification": "The Day 5 reflection is candid about tradeoffs and the remaining edges.",
        },
    ]


def _build_demo_report_citations(
    *,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
) -> list[dict[str, str]]:
    return [
        {
            "dimension": "Architecture & Design",
            "artifact_type": "design_doc",
            "artifact_ref": "day1-design-doc.md:L1-L20",
            "excerpt": "Use a small FastAPI service with one core domain module and a service layer.",
        },
        {
            "dimension": "Architecture & Design",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{bootstrap_commit_sha}:README.md:L1-L24",
            "excerpt": "Bootstrap commit created the empty repository, devcontainer, and README.",
        },
        {
            "dimension": "Problem Understanding",
            "artifact_type": "design_doc",
            "artifact_ref": "day1-design-doc.md:L21-L36",
            "excerpt": "Build a from-scratch work Trial experience that keeps every step evidence-backed.",
        },
        {
            "dimension": "Problem Understanding",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{day2_commit_sha}:src/api/trials.ts:L40-L88",
            "excerpt": "Initial implementation kickoff commit.",
        },
        {
            "dimension": "Implementation Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{day3_commit_sha}:src/services/reporting.py:L12-L76",
            "excerpt": "Wrap-up commit completed the core workflow and docs.",
        },
        {
            "dimension": "Code Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{day3_commit_sha}:src/services/reporting.py:L12-L76",
            "excerpt": "The code stays readable, compact, and easy to audit.",
        },
        {
            "dimension": "Code Quality",
            "artifact_type": "submission",
            "artifact_ref": "day3-implementation-wrap-up.md:L1-L18",
            "excerpt": "Documentation tracks the implementation and the remaining gaps are explicit.",
        },
        {
            "dimension": "Testing Discipline",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{day2_commit_sha}:tests/test_trials.ts:L1-L6",
            "excerpt": "Kickoff tests established the core workflow shape.",
        },
        {
            "dimension": "Testing Discipline",
            "artifact_type": "submission",
            "artifact_ref": "day3-implementation-wrap-up.md:L19-L30",
            "excerpt": "The final pass/fail balance shows the build was checked, not just described.",
        },
        {
            "dimension": "Development Process",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{bootstrap_commit_sha}:README.md:L1-L24",
            "excerpt": "Bootstrap commit created the empty repository, devcontainer, and README.",
        },
        {
            "dimension": "Development Process",
            "artifact_type": "code_implementation",
            "artifact_ref": f"{day2_commit_sha}:src/api/trials.ts:L40-L88",
            "excerpt": "Implementation moved in a disciplined, reviewable sequence.",
        },
        {
            "dimension": "Communication",
            "artifact_type": "transcript",
            "artifact_ref": "[00:00-02:00]",
            "excerpt": "Demo transcript with architecture, tradeoffs, and next steps.",
        },
        {
            "dimension": "Communication",
            "artifact_type": "submission",
            "artifact_ref": "day4-handoff-demo.md:L1-L18",
            "excerpt": "The handoff summary keeps the story tight and evidence-backed.",
        },
        {
            "dimension": "Reflection & Ownership",
            "artifact_type": "submission",
            "artifact_ref": "day5-reflection.md:L1-L18",
            "excerpt": "Reflection essay covering what went well, what was hard, and what changed.",
        },
        {
            "dimension": "Reflection & Ownership",
            "artifact_type": "submission",
            "artifact_ref": "day5-reflection.md:L19-L34",
            "excerpt": "The next-step plan is concrete and honest about the remaining edges.",
        },
    ]


async def _seed_trial_scaffold(
    db: AsyncSession,
    *,
    company_id: int,
    created_by: int,
    title: str,
    role: str,
    seniority: str,
    preferred_language_framework: str,
    focus: str,
    status: str,
    company_name: str,
    project_brief_md: str,
    storyline_md: str,
    ai_notice_version: str,
    trial_focus_note: str,
) -> tuple[Trial, list[Task], TrialScenarioVersion]:
    trial = Trial(
        company_id=company_id,
        title=title,
        role=role,
        preferred_language_framework=preferred_language_framework,
        seniority=seniority,
        focus=focus,
        company_context={
            "companyName": company_name,
            "preferredLanguageFramework": preferred_language_framework,
            "demoMode": "yc-demo",
        },
        company_rubric_json=_demo_company_rubrics(),
        ai_prompt_overrides_json=None,
        ai_notice_version=ai_notice_version,
        ai_notice_text="Winoe demo notice for the YC rehearsal dataset.",
        ai_eval_enabled_by_day={
            "1": True,
            "2": True,
            "3": True,
            "4": True,
            "5": True,
        },
        day_window_overrides_enabled=True,
        day_window_overrides_json={"5": {"startLocal": "09:00", "endLocal": "21:00"}},
        created_by=created_by,
        status=TRIAL_STATUS_GENERATING,
        generating_at=_now(),
    )
    db.add(trial)
    _apply_legacy_trial_fields(trial)
    await db.flush()

    tasks = await seed_default_tasks(db, trial.id, trial.template_key)
    scenario_version = await create_initial_scenario_version(
        db, trial=trial, tasks=tasks
    )
    scenario_version.storyline_md = storyline_md
    scenario_version.task_prompts_json = _demo_task_prompts(tasks)
    scenario_version.rubric_json = {
        "dimensions": [
            {"key": "architecture", "weight": 0.18},
            {"key": "scope_control", "weight": 0.10},
            {"key": "implementation_discipline", "weight": 0.16},
            {"key": "testing_discipline", "weight": 0.14},
            {"key": "code_quality", "weight": 0.12},
            {"key": "dependency_hygiene", "weight": 0.10},
            {"key": "communication_handoff_demo", "weight": 0.10},
            {"key": "reflection_self_awareness", "weight": 0.10},
        ]
    }
    scenario_version.project_brief_md = project_brief_md
    scenario_version.focus_notes = trial_focus_note
    scenario_version.preferred_language_framework = preferred_language_framework
    scenario_version.seniority = seniority
    scenario_version.locked_at = _now()
    trial.ready_for_review_at = _now()
    trial.activated_at = _now()
    trial.active_scenario_version_id = scenario_version.id
    trial.status = status
    await db.flush()
    return trial, tasks, scenario_version


async def _clear_demo_scope(db: AsyncSession, config: DemoSeedConfig) -> None:
    """Remove any existing demo-scoped rows before reseeding."""
    candidate_emails = [
        config.talent_partner_email,
        DEMO_HERO_CANDIDATE_EMAIL,
        DEMO_ACTIVE_CANDIDATE_EMAIL,
        DEMO_AWAITING_CANDIDATE_EMAIL,
    ]
    demo_trial_rows = (
        await db.execute(
            select(Trial.id, Trial.company_id).where(
                Trial.company_context["demoMode"].as_string() == DEMO_MODE_MARKER
            )
        )
    ).all()
    trial_ids = [row.id for row in demo_trial_rows]
    company_ids = sorted({row.company_id for row in demo_trial_rows})

    user_ids = (
        (await db.execute(select(User.id).where(User.email.in_(candidate_emails))))
        .scalars()
        .all()
    )

    candidate_session_filters = [CandidateSession.invite_email.in_(candidate_emails)]
    if trial_ids:
        candidate_session_filters.append(CandidateSession.trial_id.in_(trial_ids))
    candidate_session_ids = (
        (
            await db.execute(
                select(CandidateSession.id).where(or_(*candidate_session_filters))
            )
        )
        .scalars()
        .all()
    )

    scenario_version_ids: list[int] = []
    task_ids: list[int] = []
    workspace_ids: list[int] = []
    workspace_group_ids: list[int] = []
    evaluation_run_ids: list[int] = []
    recording_ids: list[int] = []
    notification_audit_ids: list[int] = []
    if trial_ids:
        scenario_version_ids = (
            (
                await db.execute(
                    select(TrialScenarioVersion.id).where(
                        TrialScenarioVersion.trial_id.in_(trial_ids)
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
    if candidate_session_ids:
        workspace_ids = (
            (
                await db.execute(
                    select(Workspace.id).where(
                        Workspace.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        workspace_group_ids = (
            (
                await db.execute(
                    select(WorkspaceGroup.id).where(
                        WorkspaceGroup.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
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
        notification_audit_ids = (
            (
                await db.execute(
                    select(NotificationDeliveryAudit.id).where(
                        NotificationDeliveryAudit.candidate_session_id.in_(
                            candidate_session_ids
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
    job_ids: list[str] = []
    if candidate_session_ids or company_ids:
        job_filters = []
        if candidate_session_ids:
            job_filters.append(Job.candidate_session_id.in_(candidate_session_ids))
        if company_ids:
            job_filters.append(Job.company_id.in_(company_ids))
        job_ids = (
            (await db.execute(select(Job.id).where(or_(*job_filters)))).scalars().all()
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

    task_draft_filters = []
    if candidate_session_ids:
        task_draft_filters.append(
            TaskDraft.candidate_session_id.in_(candidate_session_ids)
        )
    if task_ids:
        task_draft_filters.append(TaskDraft.task_id.in_(task_ids))
    if task_draft_filters:
        await db.execute(delete(TaskDraft).where(or_(*task_draft_filters)))

    if candidate_session_ids:
        if job_ids:
            await db.execute(delete(Job).where(Job.id.in_(job_ids)))
        if notification_audit_ids:
            await db.execute(
                delete(NotificationDeliveryAudit).where(
                    NotificationDeliveryAudit.id.in_(notification_audit_ids)
                )
            )
        await db.execute(
            delete(Submission).where(
                Submission.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(CandidateDayAudit).where(
                CandidateDayAudit.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(TrialEvaluationStateRecord).where(
                TrialEvaluationStateRecord.candidate_session_id.in_(
                    candidate_session_ids
                )
            )
        )
        await db.execute(
            delete(Transcript).where(Transcript.recording_id.in_(recording_ids))
        )
        await db.execute(
            delete(RecordingAsset).where(RecordingAsset.id.in_(recording_ids))
        )
        await db.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        await db.execute(
            delete(WorkspaceGroup).where(WorkspaceGroup.id.in_(workspace_group_ids))
        )
        await db.execute(
            delete(CandidateSession).where(
                CandidateSession.id.in_(candidate_session_ids)
            )
        )
    elif job_ids:
        await db.execute(delete(Job).where(Job.id.in_(job_ids)))

    if trial_ids:
        await db.execute(
            update(Trial)
            .where(Trial.id.in_(trial_ids))
            .values(
                active_scenario_version_id=None,
                pending_scenario_version_id=None,
                status=TRIAL_STATUS_GENERATING,
            )
        )

    if task_ids:
        await db.execute(delete(Task).where(Task.id.in_(task_ids)))

    if scenario_version_ids:
        await db.execute(
            delete(TrialScenarioVersion).where(
                TrialScenarioVersion.id.in_(scenario_version_ids)
            )
        )

    if trial_ids:
        await db.execute(delete(Trial).where(Trial.id.in_(trial_ids)))

    deletable_user_ids = list(user_ids)
    if user_ids:
        non_demo_trial_owner_ids = (
            (
                await db.execute(
                    select(Trial.created_by).where(
                        Trial.created_by.in_(user_ids),
                        Trial.id.notin_(trial_ids) if trial_ids else True,
                    )
                )
            )
            .scalars()
            .all()
        )
        protected_user_ids = {int(user_id) for user_id in non_demo_trial_owner_ids}
        deletable_user_ids = [
            user_id for user_id in user_ids if int(user_id) not in protected_user_ids
        ]
        if deletable_user_ids:
            await db.execute(delete(User).where(User.id.in_(deletable_user_ids)))
    if company_ids:
        remaining_trial_company_ids = (
            (
                await db.execute(
                    select(Trial.company_id).where(
                        Trial.company_id.in_(company_ids),
                        Trial.id.notin_(trial_ids) if trial_ids else True,
                    )
                )
            )
            .scalars()
            .all()
        )
        remaining_user_company_ids = (
            (
                await db.execute(
                    select(User.company_id).where(
                        User.company_id.in_(company_ids),
                        User.id.notin_(deletable_user_ids)
                        if deletable_user_ids
                        else True,
                    )
                )
            )
            .scalars()
            .all()
        )
        protected_company_ids = {
            int(company_id)
            for company_id in (
                list(remaining_trial_company_ids) + list(remaining_user_company_ids)
            )
            if company_id is not None
        }
        deletable_company_ids = [
            company_id
            for company_id in company_ids
            if int(company_id) not in protected_company_ids
        ]
        if deletable_company_ids:
            await db.execute(
                delete(Company).where(Company.id.in_(deletable_company_ids))
            )

    await db.commit()


async def _reset_database(engine: AsyncEngine) -> None:
    """Delete every application row for an explicit full reset."""
    from app.shared.database.shared_database_models_model import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            await conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
            try:
                for table in reversed(Base.metadata.sorted_tables):
                    await conn.execute(table.delete())
            finally:
                await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            return
        table_names = [
            table.name
            for table in Base.metadata.sorted_tables
            if table.name != "alembic_version"
        ]
        if table_names:
            quoted = ", ".join(f'"{name}"' for name in table_names)
            await conn.exec_driver_sql(
                f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"
            )


async def seed_yc_demo_dataset(
    db: AsyncSession,
    *,
    config: DemoSeedConfig,
    github_client: GithubClient | FakeGithubClient,
) -> DemoSeedSummary:
    """Create or replace the demo dataset in the current database."""
    await _clear_demo_scope(db, config)

    company = await db.scalar(
        select(Company).where(Company.name == config.company_name)
    )
    if company is None:
        company = Company(name=config.company_name)
        db.add(company)
        await db.flush()

    talent_partner = await db.scalar(
        select(User).where(User.email == config.talent_partner_email)
    )
    if talent_partner is None:
        talent_partner = User(
            name=config.talent_partner_name,
            email=config.talent_partner_email,
            role="talent_partner",
            company_id=company.id,
            password_hash="",
        )
        db.add(talent_partner)
        await db.flush()
    else:
        talent_partner.name = config.talent_partner_name
        talent_partner.role = "talent_partner"
        talent_partner.company_id = company.id
        await db.flush()

    qa_candidate_email = config.qa_candidate_email.strip().lower()
    qa_candidate_user = await db.scalar(
        select(User).where(User.email == qa_candidate_email)
    )
    if qa_candidate_user is None:
        qa_candidate_user = User(
            name="Candidate",
            email=qa_candidate_email,
            role="candidate",
            company_id=None,
            password_hash="",
        )
        db.add(qa_candidate_user)
        await db.flush()
    else:
        qa_candidate_user.name = "Candidate"
        qa_candidate_user.role = "candidate"
        qa_candidate_user.company_id = None
        await db.flush()

    candidate_sessions: list[CandidateSession] = []
    repo_full_names: list[str] = []

    brief_md = _demo_trial_brief_markdown(config)
    storyline_md = _demo_scenario_storyline()
    hero_candidate, active_candidate = _demo_candidate_profiles()
    awaiting_candidate = _demo_invite_candidate_profiles()["awaiting_candidate"][0]
    now = _now()

    hero_trial, hero_tasks, hero_scenario = await _seed_trial_scaffold(
        db,
        company_id=company.id,
        created_by=talent_partner.id,
        title=config.trial_title,
        role=config.trial_role,
        seniority=config.trial_seniority,
        preferred_language_framework=config.trial_preferred_language_framework,
        focus=config.trial_focus,
        status=TRIAL_STATUS_READY_FOR_REVIEW,
        company_name=config.company_name,
        project_brief_md=brief_md,
        storyline_md=storyline_md,
        ai_notice_version="yc-demo-v1",
        trial_focus_note=config.trial_focus,
    )
    hero_session = CandidateSession(
        trial_id=hero_trial.id,
        scenario_version_id=hero_scenario.id,
        candidate_user_id=None,
        candidate_name=hero_candidate.name,
        invite_email=hero_candidate.email,
        candidate_email=hero_candidate.email,
        candidate_auth0_email=hero_candidate.email,
        token=_candidate_token(config, hero_candidate),
        status="completed",
        started_at=now - timedelta(days=4),
        completed_at=now,
        claimed_at=now - timedelta(days=4),
        expires_at=now + timedelta(days=7),
        invite_email_status="sent",
        invite_email_sent_at=now - timedelta(days=4),
        invite_email_last_attempt_at=now - timedelta(days=4),
        scheduled_start_at=now - timedelta(days=4),
        candidate_timezone=config.timezone,
        github_username=hero_candidate.repo_suffix.replace("-", ""),
        consent_version="yc-demo-v1",
        consent_timestamp=now - timedelta(days=4),
        ai_notice_version="yc-demo-v1",
        day_windows_json=[
            {"dayIndex": day_index, "status": "submitted"} for day_index in range(1, 6)
        ],
        schedule_locked_at=now - timedelta(days=4),
    )
    db.add(hero_session)
    await db.flush()
    candidate_sessions.append(hero_session)

    hero_repo_result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=hero_session,
        trial=hero_trial,
        scenario_version=hero_scenario,
        task=hero_tasks[1],
        repo_prefix=config.repo_prefix,
        destination_owner=config.git_owner,
        repo_name=_candidate_repo_name(config, hero_candidate),
    )
    repo_full_names.append(hero_repo_result.repo_full_name)

    hero_day2_commit_sha = await _commit_repo_snapshot(
        github_client,
        repo_full_name=hero_repo_result.repo_full_name,
        branch=hero_repo_result.default_branch,
        parent_sha=hero_repo_result.bootstrap_commit_sha or "",
        message="chore: day 2 implementation kickoff",
        files=_hero_day2_repo_files(hero_candidate),
    )
    hero_day3_commit_sha = await _commit_repo_snapshot(
        github_client,
        repo_full_name=hero_repo_result.repo_full_name,
        branch=hero_repo_result.default_branch,
        parent_sha=hero_day2_commit_sha,
        message="chore: day 3 implementation wrap-up",
        files=_hero_day3_repo_files(hero_candidate),
    )

    hero_workspace_group = WorkspaceGroup(
        candidate_session_id=hero_session.id,
        workspace_key=config.codespace_workspace_key,
        template_repo_full_name=None,
        repo_full_name=hero_repo_result.repo_full_name,
        default_branch=hero_repo_result.default_branch,
        bootstrap_commit_sha=hero_repo_result.bootstrap_commit_sha,
        created_at=now,
    )
    db.add(hero_workspace_group)
    await db.flush()
    hero_workspace = Workspace(
        workspace_group_id=hero_workspace_group.id,
        candidate_session_id=hero_session.id,
        task_id=hero_tasks[1].id,
        template_repo_full_name=None,
        repo_full_name=hero_repo_result.repo_full_name,
        repo_id=hero_repo_result.repo_id,
        default_branch=hero_repo_result.default_branch,
        bootstrap_commit_sha=hero_repo_result.bootstrap_commit_sha,
        codespace_name=hero_repo_result.codespace_name,
        codespace_url=hero_repo_result.codespace_url,
        codespace_state=hero_repo_result.codespace_state,
        workspace_provisioning_status=hero_repo_result.workspace_provisioning_status,
        latest_commit_sha=hero_day3_commit_sha,
        last_workflow_run_id=None,
        last_workflow_conclusion=None,
        last_test_summary_json=(
            f'{{"passed": {hero_candidate.test_summary[3][0]}, "failed": {hero_candidate.test_summary[3][1]}}}'
        ),
        created_at=now,
    )
    db.add(hero_workspace)
    await db.flush()

    hero_recording_key = _candidate_recording_key(config, hero_candidate)
    hero_submissions = _candidate_submissions(
        config,
        hero_candidate,
        repo_full_name=hero_repo_result.repo_full_name,
        bootstrap_commit_sha=hero_repo_result.bootstrap_commit_sha or "",
        day2_commit_sha=hero_day2_commit_sha,
        day3_commit_sha=hero_day3_commit_sha,
        recording_key=hero_recording_key,
    )
    for day_index, task in enumerate(hero_tasks, start=1):
        submission_spec = hero_submissions[day_index]
        recording_id: int | None = None
        if day_index == 4:
            recording = RecordingAsset(
                candidate_session_id=hero_session.id,
                task_id=task.id,
                storage_key=hero_recording_key,
                content_type="video/mp4",
                bytes=2_048_000,
                asset_kind="recording",
                duration_seconds=120,
                status="ready",
                consent_version="yc-demo-v1",
                consent_timestamp=now - timedelta(days=1),
                ai_notice_version="yc-demo-v1",
                retention_expires_at=now + timedelta(days=30),
            )
            db.add(recording)
            await db.flush()
            transcript = Transcript(
                recording_id=recording.id,
                text=(
                    f"{hero_candidate.name} explained the design, tradeoffs, and next steps "
                    f"for the {config.company_name} demo."
                ),
                segments_json=[
                    {"start": 0, "end": 60, "text": hero_candidate.summary_line},
                    {
                        "start": 60,
                        "end": 120,
                        "text": "The evidence trail is grounded in the submitted artifacts.",
                    },
                ],
                model_name="demo-transcribe",
                status="ready",
            )
            db.add(transcript)
            await db.flush()
            recording_id = recording.id
            submission_spec["content_json"]["transcriptRecordingId"] = recording.id
        submission = Submission(
            candidate_session_id=hero_session.id,
            task_id=task.id,
            recording_id=recording_id,
            submitted_at=now - timedelta(days=5 - day_index),
            content_text=submission_spec["content_text"],
            content_json=submission_spec["content_json"],
            code_repo_path=submission_spec["code_repo_path"],
            commit_sha=submission_spec["commit_sha"],
            final_sha=submission_spec["commit_sha"] if day_index == 3 else None,
            workflow_run_id=(
                f"yc-demo-{hero_candidate.label}-day{day_index}"
                if day_index in {2, 3}
                else None
            ),
            workflow_run_attempt=1 if day_index in {2, 3} else None,
            workflow_run_status="completed" if day_index in {2, 3} else None,
            workflow_run_conclusion="success" if day_index in {2, 3} else None,
            workflow_run_completed_at=now if day_index in {2, 3} else None,
            diff_summary_json=submission_spec["diff_summary_json"],
            tests_passed=submission_spec["tests_passed"],
            tests_failed=submission_spec["tests_failed"],
            test_output=submission_spec["test_output"],
            last_run_at=now if day_index in {2, 3} else None,
        )
        db.add(submission)
        await db.flush()
        if day_index in {2, 3}:
            await db.execute(
                delete(CandidateDayAudit).where(
                    CandidateDayAudit.candidate_session_id == hero_session.id,
                    CandidateDayAudit.day_index == day_index,
                )
            )
            db.add(
                CandidateDayAudit(
                    candidate_session_id=hero_session.id,
                    day_index=day_index,
                    cutoff_at=now - timedelta(days=5 - day_index),
                    cutoff_commit_sha=(
                        hero_day2_commit_sha if day_index == 2 else hero_day3_commit_sha
                    ),
                    eval_basis_ref=(
                        f"{hero_repo_result.repo_full_name}@"
                        f"{hero_day2_commit_sha if day_index == 2 else hero_day3_commit_sha}"
                    ),
                )
            )
            await db.flush()

    hero_day_rows, hero_reviewer_rows = _build_report_rows(
        candidate=hero_candidate,
        repo_full_name=hero_repo_result.repo_full_name,
        bootstrap_commit_sha=hero_repo_result.bootstrap_commit_sha or "",
        day2_commit_sha=hero_day2_commit_sha,
        day3_commit_sha=hero_day3_commit_sha,
    )
    hero_report_dimensions = _build_demo_report_dimensions(hero_candidate)
    hero_report_citations = _build_demo_report_citations(
        bootstrap_commit_sha=hero_repo_result.bootstrap_commit_sha or "",
        day2_commit_sha=hero_day2_commit_sha,
        day3_commit_sha=hero_day3_commit_sha,
    )
    hero_raw_report_json = {
        "overallWinoeScore": hero_candidate.overall_score,
        "recommendation": hero_candidate.recommendation,
        "confidence": hero_candidate.confidence,
        "verdictOneLiner": (
            "Sarah's Trial is cohesive, evidence-backed, and easy to explain without overclaiming."
        ),
        "narrativeAssessment": (
            "Sarah kept the work tight and readable. The Day 1 design doc set a clear boundary, "
            "the Day 2 and Day 3 commits moved steadily, and the Day 4 transcript tied the story back "
            "to concrete artifacts. The strongest signals are architecture discipline, implementation "
            "discipline, and communication clarity. The discussable gaps are operational hardening and "
            "one more explicit edge-case pass."
        ),
        "cohortContext": (
            "This completed Trial has the densest evidence trail in the seeded demo set, with a clean chain from brief to handoff."
        ),
        "dimensions": hero_report_dimensions,
        "citations": hero_report_citations,
        "dayScores": hero_day_rows,
        "reviewerReports": hero_reviewer_rows,
    }
    hero_run = await create_run(
        db,
        candidate_session_id=hero_session.id,
        scenario_version_id=hero_scenario.id,
        model_name="demo-winoe-report",
        model_version="demo-1",
        prompt_version="demo-1",
        rubric_version="demo-1",
        day2_checkpoint_sha=hero_day2_commit_sha,
        day3_final_sha=hero_day3_commit_sha,
        cutoff_commit_sha=hero_day3_commit_sha,
        transcript_reference=f"transcript:{hero_recording_key}",
        job_id=None,
        basis_fingerprint=_stable_hex(
            hero_candidate.email, hero_repo_result.repo_full_name, "basis", length=64
        ),
        overall_winoe_score=hero_candidate.overall_score,
        recommendation=hero_candidate.internal_recommendation,
        confidence=hero_candidate.confidence,
        generated_at=now,
        raw_report_json=hero_raw_report_json,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        started_at=now - timedelta(hours=1),
        completed_at=now,
        metadata_json={
            "aiPolicyProvider": "demo-seed",
            "aiPolicySnapshotDigest": (hero_scenario.ai_policy_snapshot_json or {}).get(
                "snapshotDigest"
            ),
            "rubricSnapshots": [
                {
                    "scope": "winoe",
                    "rubricKind": "demo",
                    "rubricKey": hero_candidate.label,
                    "rubricVersion": "demo-1",
                }
            ],
        },
        commit=False,
    )
    await add_day_scores(
        db,
        run=hero_run,
        day_scores=hero_day_rows,
        commit=False,
    )
    for reviewer_row in hero_reviewer_rows:
        db.add(
            EvaluationReviewerReport(
                run_id=hero_run.id,
                reviewer_agent_key=reviewer_row["reviewer_agent_key"],
                day_index=reviewer_row["day_index"],
                submission_kind=reviewer_row["submission_kind"],
                score=reviewer_row["score"],
                dimensional_scores_json=reviewer_row["dimensional_scores_json"],
                evidence_citations_json=reviewer_row["evidence_citations_json"],
                assessment_text=reviewer_row["assessment_text"],
                strengths_json=reviewer_row["strengths_json"],
                risks_json=reviewer_row["risks_json"],
                raw_output_json={
                    "summary": hero_candidate.summary_line,
                    "candidate": hero_candidate.name,
                },
            )
        )
    marker = await upsert_marker(
        db,
        candidate_session_id=hero_session.id,
        generated_at=now,
        commit=False,
    )
    if marker.id is not None:
        await replace_report_citations(
            db,
            report_id=marker.id,
            citations=hero_report_citations,
            commit=False,
        )
    db.add(
        TrialEvaluationStateRecord(
            trial_id=hero_trial.id,
            candidate_session_id=hero_session.id,
            state=TrialEvaluationState.NOTIFICATION_SENT.value,
            correlation_id=f"demo-seed-report-ready-{hero_session.id}",
            reviewer_status_json={
                "status": "completed",
                "reviewers": [
                    "design_doc_reviewer",
                    "code_implementation_reviewer",
                    "demo_presentation_reviewer",
                    "reflection_essay_reviewer",
                    "winoe_report",
                ],
            },
            winoe_synthesis_status="completed",
            evidence_trail_validation_status="passed",
            report_finalization_status="finalized",
            notification_status="sent",
        )
    )
    hero_session.completed_at = now
    hero_session.status = "completed"
    hero_trial.completed_at = now
    hero_trial.status = TRIAL_STATUS_COMPLETED

    active_trial, active_tasks, active_scenario = await _seed_trial_scaffold(
        db,
        company_id=company.id,
        created_by=talent_partner.id,
        title="Senior Backend Engineer Trial",
        role="Senior Backend Engineer",
        seniority="senior",
        preferred_language_framework="Python + FastAPI",
        focus="Build a reliable backend surface for a five-day evidence-backed Trial.",
        status=TRIAL_STATUS_ACTIVE_INVITING,
        company_name=config.company_name,
        project_brief_md=brief_md,
        storyline_md=storyline_md,
        ai_notice_version="yc-demo-v1",
        trial_focus_note="Python + FastAPI backend with clean evidence capture.",
    )
    active_session = CandidateSession(
        trial_id=active_trial.id,
        scenario_version_id=active_scenario.id,
        candidate_user_id=qa_candidate_user.id,
        candidate_name=active_candidate.name,
        invite_email=active_candidate.email,
        candidate_email=active_candidate.email,
        candidate_auth0_email=active_candidate.email,
        token=_candidate_token(config, active_candidate),
        status="in_progress",
        started_at=now - timedelta(days=2),
        completed_at=None,
        claimed_at=now - timedelta(days=2),
        scheduled_start_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=7),
        invite_email_status="sent",
        invite_email_sent_at=now - timedelta(days=2),
        invite_email_last_attempt_at=now - timedelta(days=2),
        candidate_timezone=config.timezone,
        github_username=active_candidate.repo_suffix.replace("-", ""),
        consent_version="yc-demo-v1",
        consent_timestamp=now - timedelta(days=2),
        ai_notice_version="yc-demo-v1",
        day_windows_json=[
            {"dayIndex": 1, "status": "submitted"},
            {"dayIndex": 2, "status": "in_progress"},
            {"dayIndex": 3, "status": "locked"},
            {"dayIndex": 4, "status": "locked"},
            {"dayIndex": 5, "status": "locked"},
        ],
    )
    db.add(active_session)
    await db.flush()
    candidate_sessions.append(active_session)

    active_repo_result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=active_session,
        trial=active_trial,
        scenario_version=active_scenario,
        task=active_tasks[1],
        repo_prefix=config.repo_prefix,
        destination_owner=config.git_owner,
        repo_name=_candidate_repo_name(config, active_candidate),
    )
    repo_full_names.append(active_repo_result.repo_full_name)

    active_day2_commit_sha = await _commit_repo_snapshot(
        github_client,
        repo_full_name=active_repo_result.repo_full_name,
        branch=active_repo_result.default_branch,
        parent_sha=active_repo_result.bootstrap_commit_sha or "",
        message="chore: day 2 implementation kickoff",
        files=_active_day2_repo_files(active_candidate),
    )

    active_workspace_group = WorkspaceGroup(
        candidate_session_id=active_session.id,
        workspace_key=config.codespace_workspace_key,
        template_repo_full_name=None,
        repo_full_name=active_repo_result.repo_full_name,
        default_branch=active_repo_result.default_branch,
        bootstrap_commit_sha=active_repo_result.bootstrap_commit_sha,
        created_at=now,
    )
    db.add(active_workspace_group)
    await db.flush()
    active_workspace = Workspace(
        workspace_group_id=active_workspace_group.id,
        candidate_session_id=active_session.id,
        task_id=active_tasks[1].id,
        template_repo_full_name=None,
        repo_full_name=active_repo_result.repo_full_name,
        repo_id=active_repo_result.repo_id,
        default_branch=active_repo_result.default_branch,
        bootstrap_commit_sha=active_repo_result.bootstrap_commit_sha,
        codespace_name=active_repo_result.codespace_name,
        codespace_url=active_repo_result.codespace_url,
        codespace_state=active_repo_result.codespace_state,
        workspace_provisioning_status=active_repo_result.workspace_provisioning_status,
        latest_commit_sha=active_day2_commit_sha,
        last_workflow_run_id=None,
        last_workflow_conclusion=None,
        last_test_summary_json=None,
        created_at=now,
    )
    db.add(active_workspace)
    await db.flush()

    active_day1_submission = Submission(
        candidate_session_id=active_session.id,
        task_id=active_tasks[0].id,
        recording_id=None,
        submitted_at=now - timedelta(days=2),
        content_text=_candidate_design_doc(active_candidate),
        content_json={
            "artifactType": "design_document",
            "candidate": active_candidate.name,
            "company": config.company_name,
            "summary": active_candidate.summary_line,
        },
        code_repo_path=None,
        commit_sha=None,
        final_sha=None,
        workflow_run_id=None,
        workflow_run_attempt=None,
        workflow_run_status=None,
        workflow_run_conclusion=None,
        workflow_run_completed_at=None,
        diff_summary_json=None,
        tests_passed=None,
        tests_failed=None,
        test_output=None,
        last_run_at=None,
    )
    db.add(active_day1_submission)
    await db.flush()

    awaiting_trial, _, awaiting_scenario = await _seed_trial_scaffold(
        db,
        company_id=company.id,
        created_by=talent_partner.id,
        title="Staff Engineer Trial",
        role="Staff Engineer",
        seniority="staff",
        preferred_language_framework="Go",
        focus="Keep the architecture minimal while leaving a crisp evidence trail.",
        status=TRIAL_STATUS_ACTIVE_INVITING,
        company_name=config.company_name,
        project_brief_md=brief_md,
        storyline_md="A staff-level Trial that is ready to invite a candidate and wait for start.",
        ai_notice_version="yc-demo-v1",
        trial_focus_note="Go-oriented staff level work with an invite still pending.",
    )
    awaiting_session = CandidateSession(
        trial_id=awaiting_trial.id,
        scenario_version_id=awaiting_scenario.id,
        candidate_user_id=None,
        candidate_name=awaiting_candidate.name,
        invite_email=awaiting_candidate.email,
        candidate_email=awaiting_candidate.email,
        candidate_auth0_email=awaiting_candidate.email,
        token=_stable_hex(
            config.company_name, awaiting_candidate.email, "invite", length=32
        ),
        status="not_started",
        claimed_at=None,
        scheduled_start_at=None,
        started_at=None,
        completed_at=None,
        expires_at=now + timedelta(days=7),
        invite_email_status="sent",
        invite_email_sent_at=now - timedelta(hours=6),
        invite_email_last_attempt_at=now - timedelta(hours=6),
        candidate_timezone=config.timezone,
        github_username=awaiting_candidate.github_username,
        consent_version="yc-demo-v1",
        consent_timestamp=None,
        ai_notice_version="yc-demo-v1",
        day_windows_json=[],
    )
    db.add(awaiting_session)
    await db.flush()
    candidate_sessions.append(awaiting_session)

    for trial in (hero_trial, active_trial, awaiting_trial):
        trial.activated_at = trial.activated_at or now

    await db.commit()
    return DemoSeedSummary(
        company_id=company.id,
        trial_id=hero_trial.id,
        candidate_session_ids=[candidate.id for candidate in candidate_sessions],
        repo_full_names=repo_full_names,
    )


__all__ = [
    "DemoCandidateProfile",
    "DemoSeedConfig",
    "DemoSeedSummary",
    "_clear_demo_scope",
    "_reset_database",
    "seed_yc_demo_dataset",
]
